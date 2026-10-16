"""Tracker observations and exact proposals never become a status store."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support

spec = importlib.util.spec_from_file_location('sf_trackers',support.REPO/'adapters/trackers.py')
trackers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trackers)
FIXTURE = support.REPO/'tests/fixtures/trackers'
EVIDENCE = {'subject_sha':'a'*40,'manifest':'proof/gate.json','manifest_sha256':'b'*64}


class TrackerTests(unittest.TestCase):
    def test_ancestor_replacement_rejects_detached_source_without_external_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            inside, outside = root/'inside', root/'outside'
            inside.mkdir()
            outside.mkdir()
            source = inside/'tracker.md'
            source.write_text('captured source')
            external = outside/'tracker.md'
            external.write_text('external bytes')
            real_read = trackers.os.read
            captured = []
            def swap(fd, count):
                content = real_read(fd, count)
                if content:
                    captured.append(content)
                    inside.rename(root/'detached')
                    inside.symlink_to(outside, target_is_directory=True)
                return content
            with mock.patch.object(trackers.os, 'read', side_effect=swap), self.assertRaisesRegex(trackers.TrackerError, 'ancestor changed'):
                trackers.read(source)
            self.assertEqual([b'captured source'], captured)
            self.assertEqual('external bytes', external.read_text())

    def test_v6_observations(self):
        text = (FIXTURE/'sprint-status.yaml').read_text()
        result = trackers.observe_v6(text)
        self.assertEqual('planning-source-observation',result['authority'])
        self.assertEqual(['backlog','backlog','ready-for-dev','review','done','optional'],[e['observed_status'] for e in result['entries']])
        self.assertEqual(2,len(result['planning_links']))
        self.assertEqual(1,len(result['action_items']))

    def test_exact_proposal_epic_lift_and_idempotence(self):
        text = (FIXTURE/'sprint-status.yaml').read_text()
        for backlog in (True,False):
            original = text if backlog else text.replace('epic-1: backlog','epic-1: in-progress')
            result = trackers.propose(original,'bmad-v6','1-1-foundation','in-progress',trackers.digest(original),EVIDENCE)
            self.assertEqual(2 if backlog else 1,len(result['changes']))
            lines = original.splitlines(keepends=True)
            for patch in result['changes']:
                self.assertEqual(lines[patch['line']-1],patch['before'])
                lines[patch['line']-1] = patch['after']
            updated = ''.join(lines)
            self.assertIn('# preserve this comment',updated)
            again = trackers.propose(updated,'bmad-v6','1-1-foundation','in-progress',trackers.digest(updated),EVIDENCE)
            self.assertEqual([],again['changes'])
        with self.assertRaisesRegex(trackers.TrackerError,'regress'):
            trackers.propose(text,'bmad-v6','1-4-complete','in-progress',trackers.digest(text),EVIDENCE)
        with self.assertRaisesRegex(trackers.TrackerError,'stale'):
            trackers.propose(text,'bmad-v6','1-1-foundation','done','0'*64,EVIDENCE)

    def test_markdown_ids_and_exact_proof_bound_proposal(self):
        text = (FIXTURE/'tasks.md').read_text()
        self.assertEqual(trackers.observe_markdown(text),trackers.observe_markdown(text))
        proposal = trackers.propose(text,'markdown','STORY-2','done',trackers.digest(text),EVIDENCE)
        self.assertEqual(1,len(proposal['changes']))
        self.assertEqual(4,proposal['changes'][0]['line'])
        with self.assertRaises(trackers.TrackerError):
            trackers.propose(text,'markdown','STORY-2','done',trackers.digest(text),{})
        with self.assertRaises(trackers.TrackerError):
            trackers.observe_markdown(text+text)
        with self.assertRaises(trackers.TrackerError):
            trackers.observe_markdown('- [ ] No stable ID\n')

    def test_whitespace_empty_acceptance_and_malformed_evidence(self):
        text = (FIXTURE/'sprint-status.yaml').read_text().replace('1-1-foundation: backlog','1-1-foundation:  backlog')
        proposal = trackers.propose(text,'bmad-v6','1-1-foundation','in-progress',trackers.digest(text),EVIDENCE)
        patch = next(p for p in proposal['changes'] if '1-1-foundation' in p['before'])
        self.assertIn('1-1-foundation:  in-progress # preserve this comment',patch['after'])
        for references in (',','one.md,',',two.md',' , '):
            with self.assertRaisesRegex(trackers.TrackerError,'nonempty'):
                trackers.observe_markdown('- [ ] STORY-1: Title | ac: '+references+' | depends: -\n')
        for key in EVIDENCE:
            with self.assertRaises(trackers.TrackerError):
                trackers.propose(text,'bmad-v6','1-1-foundation','done',trackers.digest(text),{**EVIDENCE,key:None})

    def test_duplicates_unsupported_yaml_and_v7(self):
        text = (FIXTURE/'sprint-status.yaml').read_text()
        for invalid in (text+'  bad: value\n',text.replace('  1-2-feature: ready-for-dev','  1-1-foundation: done'),text.replace('backlog #','&anchor backlog #')):
            with self.assertRaises(trackers.TrackerError):
                trackers.observe_v6(invalid)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'sprint-status.yaml').write_text(text)
            self.assertEqual('bmad-v6',trackers.detect(root))
            (root/'tickets.toml').write_text('')
            with self.assertRaises(trackers.TrackerError):
                trackers.detect(root)
            self.assertEqual('bmad-v7',trackers.detect(root,'bmad-v7'))
        with self.assertRaisesRegex(trackers.TrackerError,'not implemented'):
            trackers.observe('','bmad-v7')
