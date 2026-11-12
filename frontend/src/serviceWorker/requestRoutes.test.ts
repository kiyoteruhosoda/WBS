import { describe, expect, it } from 'vitest';
import { SKIP_WAITING_MESSAGE as PAGE_SKIP_WAITING } from '../pwa/appUpdate';
import { SKIP_WAITING_MESSAGE, isShellWorthy, routeOf, shellCacheName, staleShellCaches } from './requestRoutes';

const ORIGIN = 'https://wbs.nolumia.com';
const get = (path: string, mode = 'cors') => ({ method: 'GET', url: `${ORIGIN}${path}`, mode });
const page = (path: string) => get(path, 'navigate');

describe('requests handled by the Service Worker', () => {
  it('navigations return the shell (index.html), for "today" and deep pages alike', () => {
    expect(routeOf(page('/'), ORIGIN)).toBe('shell-page');
    expect(routeOf(page('/calendar'), ORIGIN)).toBe('shell-page');
    expect(routeOf(page('/tasks/12?tab=log'), ORIGIN)).toBe('shell-page');
  });

  it('static files come from the shell (network if missing)', () => {
    expect(routeOf(get('/assets/index-abc123.js', 'no-cors'), ORIGIN)).toBe('shell-file');
    expect(routeOf(get('/manifest.webmanifest'), ORIGIN)).toBe('shell-file');
    expect(routeOf(get('/pwa-192x192.png', 'no-cors'), ORIGIN)).toBe('shell-file');
  });

  it('/api passes through: data, sign-in round trips (redirects), and the version (/api/info)', () => {
    expect(routeOf(get('/api/time-entries/current'), ORIGIN)).toBe('network');
    expect(routeOf(page('/api/auth/login?next=%2F'), ORIGIN)).toBe('network');
    expect(routeOf(page('/api/auth/callback?code=x&state=y'), ORIGIN)).toBe('network');
    expect(routeOf(get('/api/info'), ORIGIN)).toBe('network');
    expect(routeOf(page('/api'), ORIGIN)).toBe('network');
  });

  it('time-tracking app return URL (/app/oauth2redirect) and App Links verification file pass through', () => {
    expect(routeOf(page('/app/oauth2redirect?code=x&state=y'), ORIGIN)).toBe('network');
    expect(routeOf(page('/app'), ORIGIN)).toBe('network');
    expect(routeOf(get('/.well-known/assetlinks.json'), ORIGIN)).toBe('network');
  });

  it('does not pass through similarly named pages (prefix match up to a separator)', () => {
    expect(routeOf(page('/apps'), ORIGIN)).toBe('shell-page');
    expect(routeOf(page('/apiary'), ORIGIN)).toBe('shell-page');
  });

  it('the Service Worker itself, non-GET and other origins pass through', () => {
    expect(routeOf(get('/sw.js'), ORIGIN)).toBe('network');
    expect(routeOf({ method: 'POST', url: `${ORIGIN}/`, mode: 'navigate' }, ORIGIN)).toBe('network');
    expect(routeOf({ method: 'GET', url: 'https://fonts.googleapis.com/css2?family=Noto+Sans+JP', mode: 'no-cors' }, ORIGIN)).toBe('network');
  });
});

describe('shell cache', () => {
  it('on activation deletes only old shell versions (leaves other caches alone)', () => {
    const names = [shellCacheName('old1'), shellCacheName('new2'), 'other-cache'];
    expect(staleShellCaches(names, 'new2')).toEqual([shellCacheName('old1')]);
  });

  it('caches only non-redirected same-origin successes in the shell', () => {
    expect(isShellWorthy({ ok: true, redirected: false, type: 'basic' })).toBe(true);
    expect(isShellWorthy({ ok: true, redirected: true, type: 'basic' })).toBe(false);
    expect(isShellWorthy({ ok: false, redirected: false, type: 'basic' })).toBe(false);
    expect(isShellWorthy({ ok: true, redirected: false, type: 'opaque' })).toBe(false);
  });

  it('the activate-new-version message is the same in the UI and the Service Worker', () => {
    expect(PAGE_SKIP_WAITING).toBe(SKIP_WAITING_MESSAGE);
  });
});
