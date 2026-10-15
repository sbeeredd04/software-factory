"""All-page review observations and explicitly unexecuted action proposals."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_agents import fixture, helper, save

T = helper('triage')
HEAD = 'a'*40


def thread(index):
    return {'id':f'T{index}','isResolved':False,'isOutdated':False,'path':'app.py','line':3,'originalLine':3}


def comment(index):
    return {'id':f'C{index}','databaseId':index+1,'author':{'login':'fixture-review[bot]'},
            'body':'Check this\n```suggestion\n$(never-execute)\n```\n','url':'https://github.com/example/project/pull/1#discussion-'+str(index),
            'path':'app.py','line':3,'originalLine':3,'commit':{'oid':HEAD},'originalCommit':{'oid':HEAD},
            'createdAt':'2026-01-01T00:00:00Z','updatedAt':'2026-01-01T00:00:00Z'}


def envelope(rows):
    result = []
    for offset in range(0,max(1,len(rows)),100):
        after = str(offset+100) if offset+100 < len(rows) else None
        result.append({'cursor':None if offset==0 else str(offset),'exit_code':0,
                       'response':rows[offset:offset+100],'next':after})
    return result


def rest_pages(kind, rows):
    values = envelope(rows)
    endpoint = 'repos/example/project/'+('issues/1/comments' if kind == 'issues' else f'pulls/1/{kind}')
    for value in values:
        value['endpoint'] = endpoint
    return values


def capture(thread_count=1,comment_count=1):
    threads = [thread(i) for i in range(thread_count)]
    outer = envelope(threads)
    for page in outer:
        page['response'] = {'data':{'repository':{'pullRequest':{'id':'PR1','headRefOid':HEAD,'url':'https://github.com/example/project/pull/1',
            'reviewThreads':{'nodes':page['response'],'pageInfo':{'hasNextPage':page['next'] is not None,'endCursor':page['next']}}}}}}
    comments = {}
    for index,t in enumerate(threads):
        values = envelope([comment(index*1000+i) for i in range(comment_count)])
        for page in values:
            page['response'] = {'data':{'node':dict(t,comments={'nodes':page['response'],'pageInfo':{'hasNextPage':page['next'] is not None,'endCursor':page['next']}})}}
        comments[t['id']] = values
    review = {'id':1,'user':{'login':'fixture-review[bot]'},'body':'Review report','commit_id':HEAD,'state':'COMMENTED',
              'html_url':'https://github.com/example/project/pull/1#pullrequestreview-1',
              'pull_request_url':'https://api.github.com/repos/example/project/pulls/1'}
    return {'owner':'example','repo':'project','number':1,'host':'github.com','head_before':HEAD,'head_after':HEAD,
            'threads':outer,'comments':comments,'rest':{'comments':rest_pages('comments',[]),'reviews':rest_pages('reviews',[review]),'issues':rest_pages('issues',[])}}


class TriageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.data = fixture(self.root,True)

    def test_literal_read_recipes_never_execute(self):
        with mock.patch('subprocess.Popen',side_effect=AssertionError('network')):
            result = T.recipes('example','project',1)
        self.assertEqual(['gh','api','--hostname','github.com','--method','GET','--paginate','--slurp','repos/example/project/pulls/1/comments?per_page=100'],result['rest']['comments'])
        self.assertIn('query='+T.THREAD_QUERY,result['threads'])
        self.assertIn('query='+T.COMMENT_QUERY,result['comments_per_thread'])
        with self.assertRaises(T.Error):
            T.recipes('$(bad)','project',1)

    def test_outer_and_each_nested_connection_exhausted(self):
        data = capture(101,1)
        for tid in ('T0','T100'):
            extra = capture(1,101)['comments']['T0']
            for page in extra:
                page['response']['data']['node']['id'] = tid
            data['comments'][tid] = extra
        result = T.normalize(self.root,data)
        self.assertEqual(101,len(result['threads']))
        self.assertEqual(101,len(result['threads'][0]['comments']))
        self.assertEqual(101,len(result['threads'][-1]['comments']))
        self.assertEqual('observed',result['status'])
        self.assertIn('untrusted',result['threads'][0]['comments'][0]['suggestions'][0]['trust'])

    def test_missing_nested_terminal_page_and_false_complete_rejected(self):
        data = capture(1,101)
        data['comments']['T0'].pop()
        with self.assertRaises(T.Error):
            T.normalize(self.root,data)
        data = capture(101,1)
        data['threads'][0]['response']['data']['repository']['pullRequest']['reviewThreads']['pageInfo']['endCursor'] = None
        with self.assertRaises(T.Error):
            T.normalize(self.root,data)
        data = capture()
        del data['comments']['T0']
        with self.assertRaises(T.Error):
            T.normalize(self.root,data)

    def test_errors_head_changes_repeated_cursors_budget_and_foreign_scope(self):
        cases = []
        data = capture(); data['head_after'] = 'b'*40; cases.append(data)
        data = capture(); data['threads'][0]['response']['errors'] = [{'message':'private error'}]; cases.append(data)
        data = capture(); data['comments']['T0'][0]['response']['data']['node']['comments']['nodes'][0]['url'] = 'https://other.test/example/project/pull/1'; cases.append(data)
        data = capture(201); data['threads'][1]['response']['data']['repository']['pullRequest']['reviewThreads']['pageInfo']['endCursor'] = '100'; cases.append(data)
        for data in cases:
            with self.subTest(data=list(data)),self.assertRaises(T.Error):
                T.normalize(self.root,data)
        with mock.patch.object(T,'MAX_PAGES',1),self.assertRaises(T.Error):
            T.normalize(self.root,capture())

    def test_resolved_not_inferred_from_rest_and_outdated_stays_unresolved(self):
        data = capture()
        data['rest']['comments'] = rest_pages('comments',[{'id':1,'user':None,'body':'resolved','html_url':'https://github.com/example/project/pull/1#discussion-1'}])
        data['threads'][0]['response']['data']['repository']['pullRequest']['reviewThreads']['nodes'][0]['isOutdated'] = True
        data['comments']['T0'][0]['response']['data']['node']['isOutdated'] = True
        result = T.normalize(self.root,data)
        self.assertFalse(result['threads'][0]['isResolved'])
        self.assertTrue(result['threads'][0]['isOutdated'])
        self.assertIsNone(result['reports'][0]['author'])

    def test_required_report_head_and_allowlist_zero_bots(self):
        self.data['review_bots']['copilot']['required'] = True
        save(self.root,self.data)
        data = capture()
        data['rest']['reviews'][0]['response'][0]['commit_id'] = 'b'*40
        result = T.normalize(self.root,data)
        self.assertEqual(['copilot'],result['gaps'])
        self.assertEqual('blocked',result['status'])
        self.data['review_bots'] = {}
        save(self.root,self.data)
        self.assertEqual('not_applicable',T.normalize(self.root,{})['status'])

    def test_action_proposals_require_proof_and_never_write(self):
        observed = T.normalize(self.root,capture())
        decision = {'thread':'T0','category':'confirmed','evidence':'test receipt at HEAD','verified_fix_sha':HEAD,'reply':'Fixed; proof linked','resolve':True}
        with mock.patch('subprocess.Popen',side_effect=AssertionError('write')):
            result = T.actions(observed,[decision],current_head=HEAD)
        item = result['dispositions'][0]
        self.assertEqual('requires-authorization',item['status'])
        self.assertEqual({'body':'Fixed; proof linked','in_reply_to':1},item['actions'][0]['body'])
        self.assertIn('query='+T.RESOLVE_QUERY,item['actions'][1]['argv'])
        authorized = T.actions(observed,[decision],current_head=HEAD,authority_ref='decision:triage-scope')
        self.assertEqual('proposed-unexecuted',authorized['dispositions'][0]['status'])
        for change in ({'verified_fix_sha':'b'*40},{'category':'false positive'},{'evidence':''}):
            with self.assertRaises(T.Error):
                T.actions(observed,[dict(decision,**change)],current_head=HEAD)
        with self.assertRaises(T.Error):
            T.actions(observed,[decision],current_head='b'*40)

    def test_duplicate_ids_thread_state_and_rest_completion_conflicts(self):
        data = capture()
        data['comments']['T0'][0]['response']['data']['node']['isResolved'] = True
        with self.assertRaises(T.Error):
            T.normalize(self.root,data)
        data = capture()
        del data['rest']['issues'][0]['next']
        with self.assertRaises(T.Error):
            T.normalize(self.root,data)
        data = capture()
        row = data['rest']['reviews'][0]['response'][0]
        data['rest']['reviews'][0]['response'].append(dict(row,body='different'))
        with self.assertRaises(T.Error):
            T.normalize(self.root,data)

    def test_nullable_comment_locations_and_unknown_author_are_retained(self):
        data = capture()
        node = data['comments']['T0'][0]['response']['data']['node']['comments']['nodes'][0]
        node.update(author=None,line=None,originalLine=None,commit=None,originalCommit=None)
        result = T.normalize(self.root,data)
        comment = result['threads'][0]['comments'][0]
        self.assertIsNone(comment['author'])
        self.assertEqual([],comment['bots'])
        self.assertIsNone(comment['commit'])

    def test_deferral_requires_source_decision(self):
        result = T.normalize(self.root,capture())
        d = {'thread':'T0','category':'deferred-with-authorized-reason','evidence':'documented follow-up'}
        with self.assertRaises(T.Error):
            T.actions(result,[d],current_head=HEAD)
        self.assertFalse(T.actions(result,[dict(d,decision_ref='decision:defer')],current_head=HEAD)['dispositions'][0]['actions'])

    def test_caller_capture_is_not_live_authentication(self):
        result = T.normalize(self.root,copy.deepcopy(capture()))
        self.assertIn('not authenticated',result['trust'])
        self.assertEqual('needs evidence',result['threads'][0]['disposition'])

    def test_rest_endpoint_and_row_scope_required_even_for_same_head_and_author(self):
        self.data['review_bots']['copilot']['required'] = True
        save(self.root,self.data)
        for field,value in (('endpoint',None),('endpoint','repos/other/project/pulls/1/reviews'),
                            ('html_url',None),('html_url','https://github.com/other/project/pull/1#pullrequestreview-1'),
                            ('html_url','https://github.com/example/project/pull/2#pullrequestreview-1'),
                            ('pull_request_url','https://api.github.com/repos/other/project/pulls/1')):
            data = capture()
            page = data['rest']['reviews'][0]
            target = page if field == 'endpoint' else page['response'][0]
            if value is None:
                del target[field]
            else:
                target[field] = value
            with self.subTest(field=field,value=value),self.assertRaises(T.Error):
                T.normalize(self.root,data)
        data = capture()
        del data['rest']['issues'][0]['endpoint']
        with self.assertRaises(T.Error):
            T.normalize(self.root,data)

    def test_immediately_nonadvancing_rest_and_graphql_cursor_refused(self):
        data = capture()
        page = data['rest']['issues'][0]
        data['rest']['issues'] = [dict(page,cursor=None,next='A'),dict(page,cursor='A',next='A'),dict(page,cursor='A',next=None)]
        with self.assertRaises(T.Error):
            T.normalize(self.root,data)
        data = capture(201)
        data['threads'][1]['response']['data']['repository']['pullRequest']['reviewThreads']['pageInfo']['endCursor'] = '100'
        data['threads'][2]['cursor'] = '100'
        with self.assertRaises(T.Error):
            T.normalize(self.root,data)
