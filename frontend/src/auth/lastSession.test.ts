import { describe, expect, it } from 'vitest';
import { parseLastSession } from './lastSession';

const session = {
  config: { mode: 'oidc', sso_enabled: true, provider_name: 'assay', login_path: '/api/auth/login' },
  user: { user_id: 7, email: 'a@example.com', display_name: 'A', timezone: 'Asia/Tokyo', language: 'ja' },
};

describe('最後にログインしていた人の控え', () => {
  it('控えた形なら読める', () => {
    expect(parseLastSession(JSON.stringify(session))).toEqual(session);
  });

  it('無い・壊れている・形が違うものは無いことにする', () => {
    expect(parseLastSession(null)).toBeNull();
    expect(parseLastSession('')).toBeNull();
    expect(parseLastSession('{not json')).toBeNull();
    expect(parseLastSession('null')).toBeNull();
    expect(parseLastSession(JSON.stringify({ config: session.config }))).toBeNull();
    expect(parseLastSession(JSON.stringify({ ...session, user: { ...session.user, user_id: '7' } }))).toBeNull();
  });
});
