import { describe, expect, it } from 'vitest';
import { SKIP_WAITING_MESSAGE as PAGE_SKIP_WAITING } from '../pwa/appUpdate';
import { SKIP_WAITING_MESSAGE, isShellWorthy, routeOf, shellCacheName, staleShellCaches } from './requestRoutes';

const ORIGIN = 'https://wbs.nolumia.com';
const get = (path: string, mode = 'cors') => ({ method: 'GET', url: `${ORIGIN}${path}`, mode });
const page = (path: string) => get(path, 'navigate');

describe('Service Worker が手を出す要求', () => {
  it('画面の遷移は殻（index.html）を返す。「今日」も深い画面も', () => {
    expect(routeOf(page('/'), ORIGIN)).toBe('shell-page');
    expect(routeOf(page('/calendar'), ORIGIN)).toBe('shell-page');
    expect(routeOf(page('/tasks/12?tab=log'), ORIGIN)).toBe('shell-page');
  });

  it('静的ファイルは殻から（無ければネットワーク）', () => {
    expect(routeOf(get('/assets/index-abc123.js', 'no-cors'), ORIGIN)).toBe('shell-file');
    expect(routeOf(get('/manifest.webmanifest'), ORIGIN)).toBe('shell-file');
    expect(routeOf(get('/pwa-192x192.png', 'no-cors'), ORIGIN)).toBe('shell-file');
  });

  it('/api は素通し。データも、ログインの往復（転送）も、版（/api/info）も', () => {
    expect(routeOf(get('/api/time-entries/current'), ORIGIN)).toBe('network');
    expect(routeOf(page('/api/auth/login?next=%2F'), ORIGIN)).toBe('network');
    expect(routeOf(page('/api/auth/callback?code=x&state=y'), ORIGIN)).toBe('network');
    expect(routeOf(get('/api/info'), ORIGIN)).toBe('network');
    expect(routeOf(page('/api'), ORIGIN)).toBe('network');
  });

  it('打刻アプリの戻り先（/app/oauth2redirect）と App Links の検証ファイルは素通し', () => {
    expect(routeOf(page('/app/oauth2redirect?code=x&state=y'), ORIGIN)).toBe('network');
    expect(routeOf(page('/app'), ORIGIN)).toBe('network');
    expect(routeOf(get('/.well-known/assetlinks.json'), ORIGIN)).toBe('network');
  });

  it('似た名前の画面までは素通しにしない（頭の一致は区切りまで）', () => {
    expect(routeOf(page('/apps'), ORIGIN)).toBe('shell-page');
    expect(routeOf(page('/apiary'), ORIGIN)).toBe('shell-page');
  });

  it('Service Worker 自身・GET 以外・よそのオリジンは素通し', () => {
    expect(routeOf(get('/sw.js'), ORIGIN)).toBe('network');
    expect(routeOf({ method: 'POST', url: `${ORIGIN}/`, mode: 'navigate' }, ORIGIN)).toBe('network');
    expect(routeOf({ method: 'GET', url: 'https://fonts.googleapis.com/css2?family=Noto+Sans+JP', mode: 'no-cors' }, ORIGIN)).toBe('network');
  });
});

describe('殻のキャッシュ', () => {
  it('有効になった版のとき、古い版の殻だけを消す（よそのキャッシュには触らない）', () => {
    const names = [shellCacheName('old1'), shellCacheName('new2'), 'other-cache'];
    expect(staleShellCaches(names, 'new2')).toEqual([shellCacheName('old1')]);
  });

  it('殻に入れるのは、転送されていない同じオリジンの成功だけ', () => {
    expect(isShellWorthy({ ok: true, redirected: false, type: 'basic' })).toBe(true);
    expect(isShellWorthy({ ok: true, redirected: true, type: 'basic' })).toBe(false);
    expect(isShellWorthy({ ok: false, redirected: false, type: 'basic' })).toBe(false);
    expect(isShellWorthy({ ok: true, redirected: false, type: 'opaque' })).toBe(false);
  });

  it('新しい版を有効にする合図は、画面と Service Worker で同じ値', () => {
    expect(PAGE_SKIP_WAITING).toBe(SKIP_WAITING_MESSAGE);
  });
});
