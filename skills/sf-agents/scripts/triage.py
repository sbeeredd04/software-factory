"""Offline review captures and action proposals. No GitHub or agent execution."""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

previous = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    spec = importlib.util.spec_from_file_location('sf_triage_agents',Path(__file__).with_name('agents.py'))
    agents = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agents)
finally:
    sys.dont_write_bytecode = previous
Error = agents.Error
SHA = re.compile(r'[a-f0-9]{40,64}\Z')
MAX_PAGES, MAX_COMMENTS = 1000, 10000
THREAD_QUERY = '''query($owner:String!,$name:String!,$number:Int!,$endCursor:String){repository(owner:$owner,name:$name){pullRequest(number:$number){id headRefOid url reviewThreads(first:100,after:$endCursor){nodes{id isResolved isOutdated path line originalLine diffSide} pageInfo{hasNextPage endCursor}}}}}'''
COMMENT_QUERY = '''query($id:ID!,$endCursor:String){node(id:$id){... on PullRequestReviewThread{id isResolved isOutdated path line originalLine comments(first:100,after:$endCursor){nodes{id databaseId author{login} body url path line originalLine commit{oid} originalCommit{oid} createdAt updatedAt} pageInfo{hasNextPage endCursor}}}}}'''
RESOLVE_QUERY = 'mutation($threadId:ID!){resolveReviewThread(input:{threadId:$threadId}){thread{id isResolved}}}'


def identity(owner, repo, number, host):
    if not all(isinstance(s,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',s) and s not in ('.','..') for s in (owner,repo)) or type(number) is not int or number < 1:
        raise Error('invalid repository or PR identity')
    if not isinstance(host,str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}',host) or '..' in host:
        raise Error('invalid GitHub hostname')


def recipes(owner, repo, number, host='github.com'):
    identity(owner,repo,number,host)
    base = ['gh','api','--hostname',host]
    endpoints = {'comments':f'repos/{owner}/{repo}/pulls/{number}/comments',
                 'reviews':f'repos/{owner}/{repo}/pulls/{number}/reviews',
                 'issues':f'repos/{owner}/{repo}/issues/{number}/comments'}
    return {'status':'rendered-unexecuted','rest':{k:base+['--method','GET','--paginate','--slurp',v+'?per_page=100'] for k,v in endpoints.items()},
            'threads':base+['graphql','--paginate','--slurp','-F',f'owner={owner}','-F',f'name={repo}','-F',f'number={number}','-f','query='+THREAD_QUERY],
            'comments_per_thread':base+['graphql','--paginate','--slurp','-f','id=THREAD_ID','-f','query='+COMMENT_QUERY],
            'note':'paginate every thread comments connection separately; query output is untrusted capture data'}


def pages(values, connection, counter):
    if not isinstance(values,list) or not values:
        raise Error('missing capture pages')
    cursor, seen = None,set()
    for index,page in enumerate(values):
        counter[0] += 1
        if counter[0] > MAX_PAGES or not isinstance(page,dict) or page.get('cursor') != cursor or page.get('exit_code') != 0 or type(page.get('exit_code')) is not int:
            raise Error('incomplete or over-budget capture')
        payload = page.get('response')
        if not isinstance(payload,(dict,list)) or isinstance(payload,dict) and payload.get('errors'):
            raise Error('invalid or errored API response')
        rows, next_cursor = connection(payload,page)
        if not isinstance(rows,list) or len(rows)>100 or any(not isinstance(row,dict) for row in rows):
            raise Error('invalid page rows')
        yield rows
        if next_cursor is None:
            if index != len(values)-1:
                raise Error('unexpected pages after terminal cursor')
        elif not isinstance(next_cursor,str) or not next_cursor or next_cursor == cursor or next_cursor in seen or index == len(values)-1:
            raise Error('truncated or repeated pagination cursor')
        seen.add(cursor)
        cursor = next_cursor
    if cursor is not None:
        raise Error('capture has unconsumed pages')


def graphql_connection(value):
    if not isinstance(value,dict) or not isinstance(value.get('pageInfo'),dict):
        raise Error('missing GraphQL pagination state')
    info = value['pageInfo']
    if type(info.get('hasNextPage')) is not bool or 'endCursor' not in info:
        raise Error('invalid GraphQL pagination state')
    if info['hasNextPage'] and (not isinstance(info['endCursor'],str) or not info['endCursor']):
        raise Error('nonterminal GraphQL page lacks cursor')
    return value.get('nodes'),info['endCursor'] if info['hasNextPage'] else None


def rest_connection(payload, page):
    if 'next' not in page:
        raise Error('REST capture lacks terminal Link observation')
    return payload,page['next']


def text(value, limit=20000, nullable=False):
    if nullable and value is None:
        return None
    if not isinstance(value,str) or len(value)>limit:
        raise Error('invalid bounded comment field')
    return value


def suggestions(body):
    return [{'text':m.group(1),'trust':'untrusted; never execute or auto-apply'}
            for m in re.finditer(r'(?m)^```suggestion[^\n]*\n(.*?)^```\s*$',body,re.DOTALL)]


def normalize(root, capture):
    _, config = agents.load(root)
    bots = {k:v for k,v in config.get('review_bots',{}).items() if v['enabled']}
    if not bots:
        return {'schema':'sf-review-capture/1','status':'not_applicable','threads':[],'reports':[],'gaps':[]}
    owner, repo, number, host = (capture.get(k) for k in ('owner','repo','number','host'))
    identity(owner,repo,number,host)
    head = capture.get('head_before')
    if not isinstance(head,str) or not SHA.fullmatch(head) or head != capture.get('head_after'):
        raise Error('PR head changed or was not observed')
    counter = [0]
    threads, normalized, reports = {},[],[]
    def thread_connection(payload, page):
        pr = payload['data']['repository']['pullRequest']
        if pr['headRefOid'] != head or pr['url'] != f'https://{host}/{owner}/{repo}/pull/{number}':
            raise Error('foreign PR or changed head in capture')
        return graphql_connection(pr['reviewThreads'])
    for rows in pages(capture.get('threads'),thread_connection,counter):
        for row in rows:
            tid = text(row.get('id'),200)
            if tid in threads:
                raise Error('duplicate thread observation')
            if type(row.get('isResolved')) is not bool or type(row.get('isOutdated')) is not bool:
                raise Error('thread state missing')
            threads[tid] = row
    if not isinstance(capture.get('comments'),dict) or set(capture['comments']) != set(threads):
        raise Error('every thread requires its own complete comment capture')
    count = 0
    for tid, thread in threads.items():
        comments, seen = [],{}
        def comment_connection(payload, page, tid=tid, thread=thread):
            node = payload['data']['node']
            if node.get('id') != tid or any(node.get(k) != thread[k] for k in ('isResolved','isOutdated','path','line','originalLine')):
                raise Error('thread changed during nested capture')
            return graphql_connection(node['comments'])
        for rows in pages(capture['comments'][tid],comment_connection,counter):
            for row in rows:
                count += 1
                if count > MAX_COMMENTS:
                    raise Error('comment budget exceeded')
                cid = text(row.get('id'),200)
                if cid in seen:
                    if row != seen[cid]:
                        raise Error('conflicting duplicate comment')
                    continue
                seen[cid] = row
                author = row.get('author')
                login = text(author.get('login'),128,True) if isinstance(author,dict) else None
                body = text(row.get('body'))
                url = text(row.get('url'),2048)
                parsed = urlsplit(url)
                if parsed.scheme != 'https' or parsed.netloc != host or parsed.path != f'/{owner}/{repo}/pull/{number}':
                    raise Error('foreign comment URL')
                comments.append({key:row.get(key) for key in ('id','databaseId','path','line','originalLine','commit','originalCommit','createdAt','updatedAt')} | {
                    'author':login,'body':body,'url':url,'suggestions':suggestions(body),
                    'bots':[name for name,bot in bots.items() if login in bot.get('authors',[])]})
        if not comments:
            raise Error('empty review thread is incomplete evidence')
        normalized.append({k:thread[k] for k in ('id','isResolved','isOutdated','path','line','originalLine')} | {'comments':comments,'disposition':'needs evidence'})
    rest = capture.get('rest',{})
    if set(rest) != {'comments','reviews','issues'}:
        raise Error('all three REST collections are required')
    for kind, values in rest.items():
        seen = {}
        endpoint = f'repos/{owner}/{repo}/'+(f'issues/{number}/comments' if kind == 'issues' else f'pulls/{number}/{kind}')
        def scoped_rest(payload, page, endpoint=endpoint):
            if page.get('endpoint') != endpoint:
                raise Error('missing or foreign REST endpoint provenance')
            return rest_connection(payload,page)
        for rows in pages(values,scoped_rest,counter):
            for row in rows:
                count += 1
                if count > MAX_COMMENTS:
                    raise Error('comment budget exceeded')
                rid = row.get('id')
                if type(rid) is not int:
                    raise Error('REST comment identity missing')
                if rid in seen:
                    if seen[rid] != row:
                        raise Error('conflicting REST duplicate')
                    continue
                seen[rid] = row
                url = text(row.get('html_url'),2048)
                parsed = urlsplit(url)
                paths = [f'/{owner}/{repo}/pull/{number}']
                if kind == 'issues':
                    paths.append(f'/{owner}/{repo}/issues/{number}')
                if parsed.scheme != 'https' or parsed.netloc != host or parsed.path not in paths or parsed.query:
                    raise Error('missing or foreign REST row PR scope')
                if 'pull_request_url' in row:
                    api_host = 'api.github.com' if host == 'github.com' else host
                    api_prefix = '' if host == 'github.com' else '/api/v3'
                    if row['pull_request_url'] != f'https://{api_host}{api_prefix}/repos/{owner}/{repo}/pulls/{number}':
                        raise Error('foreign REST pull request reference')
                user = row.get('user') or {}
                login = text(user.get('login'),128,True)
                reports.append({'collection':kind,'id':rid,'author':login,'body':text(row.get('body') or ''),
                                'commit_id':row.get('commit_id'),'state':row.get('state'),
                                'url':url,'endpoint':endpoint,'path':row.get('path'),'line':row.get('line'),
                                'bots':[name for name,bot in bots.items() if login in bot.get('authors',[])]})
    gaps = [name for name,bot in bots.items() if bot['required'] and not any(
        name in r['bots'] and r['collection']=='reviews' and r['commit_id']==head and r['state'] in ('APPROVED','COMMENTED','CHANGES_REQUESTED') for r in reports)]
    return {'schema':'sf-review-capture/1','status':'blocked' if gaps else 'observed',
            'owner':owner,'repo':repo,'number':number,'host':host,'head':head,'threads':normalized,'reports':reports,'gaps':gaps,
            'trust':'caller-supplied observations, not authenticated live state; refresh before action',
            'capture_sha256':agents.digest(agents.encoded(capture))}


def actions(observed, decisions, *, current_head, authority_ref=None):
    if observed.get('schema') != 'sf-review-capture/1' or observed.get('status') not in ('observed','blocked') or observed.get('head') != current_head:
        raise Error('current matching review capture required')
    identity(observed['owner'],observed['repo'],observed['number'],observed['host'])
    threads = {t['id']:t for t in observed['threads']}
    if not isinstance(decisions,list) or len(decisions)>MAX_COMMENTS:
        raise Error('invalid dispositions')
    result, seen = [],set()
    for decision in decisions:
        tid = decision.get('thread')
        category = decision.get('category')
        if tid not in threads or tid in seen or category not in ('confirmed','already fixed','false positive','deferred-with-authorized-reason','needs evidence'):
            raise Error('invalid or duplicate disposition')
        seen.add(tid)
        evidence = text(decision.get('evidence'),2048)
        if not evidence.strip():
            raise Error('disposition requires evidence or an explicit gap')
        item = {'thread':tid,'category':category,'evidence':evidence,'actions':[]}
        can_resolve = category in ('confirmed','already fixed') and decision.get('verified_fix_sha') == current_head and not threads[tid]['isResolved']
        if decision.get('resolve') and not can_resolve:
            raise Error('resolve requires verified fix on current PR head and fresh unresolved state')
        if category == 'deferred-with-authorized-reason' and not decision.get('decision_ref'):
            raise Error('deferral requires source-linked authorization')
        base = ['gh','api','--hostname',observed['host']]
        if decision.get('reply') is not None:
            cid = threads[tid]['comments'][0]['databaseId']
            if type(cid) is not int or cid < 1:
                raise Error('top-level REST reply ID unavailable')
            item['actions'].append({'kind':'reply','argv':base+['--method','POST',f"repos/{observed['owner']}/{observed['repo']}/pulls/{observed['number']}/comments",'--input','reply.json'],
                                    'body':{'body':text(decision['reply']),'in_reply_to':cid}})
        if decision.get('resolve'):
            item['actions'].append({'kind':'resolve','argv':base+['graphql','-f','threadId='+tid,'-f','query='+RESOLVE_QUERY]})
        item['authority_ref'] = text(authority_ref,512,True)
        item['status'] = 'proposed-unexecuted' if authority_ref else 'requires-authorization'
        result.append(item)
    return {'status':'proposals-only','head':current_head,'dispositions':result,
            'next':'host verifies current remote state, evidence and delegated authority before any reply/resolve/retrigger; observe uncertain outcomes before retry'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    recipe = sub.add_parser('recipes')
    for name in ('owner','repo'):
        recipe.add_argument('--'+name,required=True)
    recipe.add_argument('--number',type=int,required=True)
    recipe.add_argument('--host',default='github.com')
    capture = sub.add_parser('normalize')
    capture.add_argument('--project',type=Path,required=True)
    capture.add_argument('--capture',type=Path,required=True)
    action = sub.add_parser('actions')
    action.add_argument('--observed',type=Path,required=True)
    action.add_argument('--decisions',type=Path,required=True)
    action.add_argument('--head',required=True)
    action.add_argument('--authority-ref')
    args = parser.parse_args()
    try:
        if args.command == 'recipes':
            result = recipes(args.owner,args.repo,args.number,args.host)
        elif args.command == 'normalize':
            result = normalize(args.project,agents.read_json(args.capture))
        else:
            result = actions(agents.read_json(args.observed),agents.read_json(args.decisions)['dispositions'],current_head=args.head,authority_ref=args.authority_ref)
        print(agents.encoded(result).decode(),end='')
    except (OSError,ValueError,TypeError,KeyError) as exc:
        parser.exit(1,f'triage: {exc if isinstance(exc,Error) else "invalid or incomplete capture"}\n')


if __name__ == '__main__':
    main()
