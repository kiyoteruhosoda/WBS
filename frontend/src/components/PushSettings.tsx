import React, { useCallback, useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Box, Button, Chip, FormControlLabel, MenuItem, Switch, TextField,
} from '@mui/material';
import {
  getPushConfig, getPushPreferences, listPushDevices, pushApi, removePushDevice,
  setDeviceReceivesCalendar, updatePushPreferences,
} from '../api/push';
import type { PushDevice, PushPreferences } from '../api/push';
import {
  browserPushEnvironment, disableOnThisDevice, enableOnThisDevice, thisDeviceLabel, thisDeviceOf, thisDeviceState,
} from '../pwa/webPush';
import type { ThisDeviceState } from '../pwa/webPush';
import { useI18n } from '../i18n';
import type { TranslationKey } from '../i18n/translations';
import { ds } from '../theme';
import { formatDate } from '../utils/format';
import { useInPageAlarmSetting } from '../preferences/inPageAlarm';
import { usePushCoversAlarms } from '../alarms/usePushCoversAlarms';

const card = {
  bgcolor: ds.paper,
  border: `1px solid ${ds.border}`,
  borderRadius: '10px',
} as const;

const sectionHeader = {
  px: '18px', py: '14px', borderBottom: `1px solid ${ds.borderPale}`,
  fontSize: 15, fontWeight: 700, color: ds.text,
} as const;

const help = { fontSize: 12, color: ds.textSub, lineHeight: 1.6 } as const;

type KindKey = 'event_alarm' | 'routine_start' | 'timer_left_running' | 'closing_due';
const KINDS: KindKey[] = ['event_alarm', 'routine_start', 'timer_left_running', 'closing_due'];
const kindPatch = (kind: KindKey, on: boolean): Partial<PushPreferences> => {
  const patch: Partial<PushPreferences> = {};
  patch[kind] = on;
  return patch;
};
const HOURS = Array.from({ length: 24 }, (_, i) => i + 1);

const PREFERENCES_KEY = ['push', 'preferences'] as const;
const DEVICES_KEY = ['push', 'devices'] as const;
/** この端末の購読の送り先（画面の中で知らせるかの判断が読む。InPageAlarm） */
const THIS_DEVICE_KEY = ['push', 'thisDevice'] as const;

const dateTime = (iso: string | null): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  return `${formatDate(d)} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};

const errorDetail = (error: unknown): string => {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  return error instanceof Error ? error.message : String(error);
};

/**
 * 設定画面の「端末への通知」（task #193・ADR-0031）。この端末で受け取る / 止める・知らせるもの・受け取る端末の一覧。
 */
const PushSettings: React.FC = () => {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [env] = useState(browserPushEnvironment);
  const inPageAlarm = useInPageAlarmSetting();
  const pushCoversAlarms = usePushCoversAlarms();

  const config = useQuery({ queryKey: ['push', 'config'], queryFn: getPushConfig });
  const preferences = useQuery({ queryKey: PREFERENCES_KEY, queryFn: getPushPreferences });
  const devices = useQuery({ queryKey: DEVICES_KEY, queryFn: listPushDevices });

  const [device, setDevice] = useState<{ state: ThisDeviceState; endpoint: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 押したのに許可が下りなかった（確認が出なかった・閉じた・拒否した）ことを知らせる。黙って戻ると押しても効かないように見える
  const [notGranted, setNotGranted] = useState(false);
  const enabledOnServer = config.data?.enabled ?? false;

  const refreshDevice = useCallback(async () => {
    setDevice(await thisDeviceState(env, enabledOnServer));
  }, [env, enabledOnServer]);

  useEffect(() => {
    if (config.data) void refreshDevice();
  }, [config.data, refreshDevice]);

  const toggleThisDevice = useMutation({
    mutationFn: async (on: boolean): Promise<ThisDeviceState | null> => {
      if (on) return (await enableOnThisDevice(env, pushApi, thisDeviceLabel())).state;
      await disableOnThisDevice(env, pushApi, devices.data ?? []);
      return null;
    },
    onMutate: () => {
      setError(null);
      setNotGranted(false);
    },
    onSuccess: (result) => setNotGranted(result === 'off' || result === 'denied'),
    onError: (e) => setError(errorDetail(e)),
    onSettled: async () => {
      await refreshDevice();
      await qc.invalidateQueries({ queryKey: DEVICES_KEY });
      await qc.invalidateQueries({ queryKey: THIS_DEVICE_KEY });
    },
  });

  const savePreferences = useMutation({
    mutationFn: (patch: Partial<PushPreferences>) => updatePushPreferences(patch),
    onSuccess: (data) => qc.setQueryData(PREFERENCES_KEY, data),
    onError: (e) => setError(errorDetail(e)),
  });

  const changeDevice = useMutation({
    mutationFn: ({ id, receivesCalendar }: { id: number; receivesCalendar: boolean }) =>
      setDeviceReceivesCalendar(id, receivesCalendar),
    onError: (e) => setError(errorDetail(e)),
    onSettled: () => qc.invalidateQueries({ queryKey: DEVICES_KEY }),
  });

  const removeDevice = useMutation({
    mutationFn: async (target: PushDevice) => {
      // この端末の登録なら、ブラウザの購読もやめる
      if (device?.endpoint != null && target.endpoint === device.endpoint) {
        await disableOnThisDevice(env, pushApi, [target]);
      } else {
        await removePushDevice(target.id);
      }
    },
    onError: (e) => setError(errorDetail(e)),
    onSettled: async () => {
      await refreshDevice();
      await qc.invalidateQueries({ queryKey: DEVICES_KEY });
      await qc.invalidateQueries({ queryKey: THIS_DEVICE_KEY });
    },
  });

  if (config.isLoading) return null;
  if (config.isError) return <Alert severity="error">{t('common.loadError')}</Alert>;

  const prefs = preferences.data;
  const list = devices.data ?? [];
  const mine = thisDeviceOf(list, device?.endpoint ?? null);
  // ブラウザに購読が残っていても、サーバの一覧に無い（別の端末から外した）なら受け取っていない
  const state: ThisDeviceState = device?.state === 'on' && devices.isSuccess && mine == null
    ? 'off'
    : device?.state ?? 'off';
  const busy = toggleThisDevice.isPending;

  return (
    <Box sx={card}>
      <Box sx={sectionHeader}>{t('push.title')}</Box>
      <Box sx={{ p: '18px', display: 'flex', flexDirection: 'column', gap: '18px' }}>
        <Box sx={help}>{t('push.lead')}</Box>

        {!enabledOnServer ? (
          <Alert severity="info">{t('push.unavailable')}</Alert>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <Box sx={{ fontSize: 14, color: ds.text }}>
              {t(`push.state.${state === 'unavailable' ? 'off' : state}` as TranslationKey)}
            </Box>
            {(state === 'off' || state === 'denied') && (
              <Button
                variant="contained"
                disabled={busy}
                onClick={() => toggleThisDevice.mutate(true)}
                sx={{ alignSelf: 'flex-start', px: '20px' }}
              >
                {t('push.enable')}
              </Button>
            )}
            {state === 'on' && (
              <Button
                variant="outlined"
                disabled={busy}
                onClick={() => toggleThisDevice.mutate(false)}
                sx={{ alignSelf: 'flex-start', px: '20px' }}
              >
                {t('push.disable')}
              </Button>
            )}
          </Box>
        )}

        {notGranted && <Alert severity="warning" onClose={() => setNotGranted(false)}>{t('push.notGranted')}</Alert>}

        <Box>
          <FormControlLabel
            sx={{ mr: 0 }}
            control={(
              <Switch
                checked={inPageAlarm.enabled}
                onChange={(e) => inPageAlarm.setEnabled(e.target.checked)}
              />
            )}
            label={<Box sx={{ fontSize: 14 }}>{t('inPageAlarm.setting')}</Box>}
          />
          <Box sx={help}>
            {t(pushCoversAlarms && inPageAlarm.enabled ? 'inPageAlarm.settingCovered' : 'inPageAlarm.settingHelp')}
          </Box>
        </Box>

        {error && <Alert severity="error" onClose={() => setError(null)}>{t('push.error', { detail: error })}</Alert>}

        {prefs && (
          <Box>
            <Box sx={{ fontSize: 13, fontWeight: 700, color: ds.text, mb: '6px' }}>{t('push.kinds')}</Box>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {KINDS.map((kind) => (
                <Box key={kind} sx={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                  <FormControlLabel
                    sx={{ mr: 0, minWidth: 180 }}
                    control={(
                      <Switch
                        checked={prefs[kind]}
                        onChange={(e) => savePreferences.mutate(kindPatch(kind, e.target.checked))}
                      />
                    )}
                    label={<Box sx={{ fontSize: 14 }}>{t(`push.kind.${kind}` as TranslationKey)}</Box>}
                  />
                  <Box sx={{ ...help, flex: '1 1 200px' }}>{t(`push.kind.${kind}Help` as TranslationKey)}</Box>
                  {kind === 'timer_left_running' && (
                    <TextField
                      select
                      size="small"
                      value={prefs.timer_left_running_hours}
                      disabled={!prefs.timer_left_running}
                      onChange={(e) => savePreferences.mutate({ timer_left_running_hours: Number(e.target.value) })}
                      sx={{ width: 110 }}
                      slotProps={{ htmlInput: { 'aria-label': t('push.kind.timer_left_running') } }}
                    >
                      {HOURS.map((h) => <MenuItem key={h} value={h}>{t('push.hours', { hours: h })}</MenuItem>)}
                    </TextField>
                  )}
                </Box>
              ))}
            </Box>
          </Box>
        )}

        <Box>
          <Box sx={{ fontSize: 13, fontWeight: 700, color: ds.text, mb: '6px' }}>{t('push.devices')}</Box>
          {list.length === 0 ? (
            <Box sx={help}>{t('push.devicesEmpty')}</Box>
          ) : (
            <Box sx={{ display: 'flex', flexDirection: 'column', border: `1px solid ${ds.borderPale}`, borderRadius: '8px' }}>
              {list.map((d, i) => (
                <Box
                  key={d.id}
                  sx={{
                    display: 'flex', flexDirection: 'column', gap: '6px', p: '12px 14px',
                    borderTop: i === 0 ? 'none' : `1px solid ${ds.borderPale}`,
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <Box sx={{ fontSize: 14, fontWeight: 600, color: ds.text }}>{d.label}</Box>
                    {mine?.id === d.id && <Chip size="small" color="primary" variant="outlined" label={t('push.thisDevice')} />}
                    <Box sx={{ flex: 1 }} />
                    <Button
                      size="small"
                      color="error"
                      disabled={removeDevice.isPending}
                      onClick={() => removeDevice.mutate(d)}
                    >
                      {t('push.remove')}
                    </Button>
                  </Box>
                  <Box sx={help}>
                    {t('push.registeredAt', { date: dateTime(d.created_at) })}
                    {' ・ '}
                    {t('push.lastSentAt', { date: dateTime(d.last_sent_at) })}
                  </Box>
                  <FormControlLabel
                    sx={{ mr: 0 }}
                    control={(
                      <Switch
                        size="small"
                        checked={d.receives_calendar}
                        onChange={(e) => changeDevice.mutate({ id: d.id, receivesCalendar: e.target.checked })}
                      />
                    )}
                    label={<Box sx={{ fontSize: 13 }}>{t('push.receivesCalendar')}</Box>}
                  />
                  <Box sx={{ ...help, mt: '-4px' }}>{t('push.receivesCalendarHelp')}</Box>
                </Box>
              ))}
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
};

export default PushSettings;
