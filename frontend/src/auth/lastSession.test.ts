import { describe, expect, it } from 'vitest';
import { parseLastSession } from './lastSession';

const session = {
  config: { mode: 'oidc', sso_enabled: true, provider_name: 'assay', login_path: '/api/auth/login' },
  user: { user_id: 7, email: 'a@example.com', display_name: 'A', timezone: 'Asia/Tokyo', language: 'ja' },
};

describe('saved copy of the last signed-in user', () => {
  it('reads data in the saved shape', () => {
    expect(parseLastSession(JSON.stringify(session))).toEqual(session);
  });

  it('treats missing, corrupt or wrong-shaped data as absent', () => {
    expect(parseLastSession(null)).toBeNull();
    expect(parseLastSession('')).toBeNull();
    expect(parseLastSession('{not json')).toBeNull();
    expect(parseLastSession('null')).toBeNull();
    expect(parseLastSession(JSON.stringify({ config: session.config }))).toBeNull();
    expect(parseLastSession(JSON.stringify({ ...session, user: { ...session.user, user_id: '7' } }))).toBeNull();
  });
});
