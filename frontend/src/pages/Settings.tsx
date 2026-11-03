import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Autocomplete, Box, Button, CircularProgress, MenuItem, TextField,
} from '@mui/material';
import { getAppInfo, getSettings, updateSettings } from '../api/settings';
import { useI18n } from '../i18n';
import { ds } from '../theme';

const card = {
  bgcolor: ds.paper,
  border: `1px solid ${ds.border}`,
  borderRadius: '10px',
} as const;

const sectionHeader = {
  px: '18px', py: '14px', borderBottom: `1px solid ${ds.borderPale}`,
  fontSize: 15, fontWeight: 700, color: ds.text,
} as const;

const FALLBACK_TIMEZONES = [
  'Asia/Tokyo', 'UTC', 'America/New_York', 'America/Los_Angeles',
  'Europe/London', 'Europe/Paris', 'Asia/Shanghai', 'Asia/Singapore', 'Australia/Sydney',
];

const timezoneOptions = (): string[] => {
  try {
    return Intl.supportedValuesOf('timeZone');
  } catch {
    return FALLBACK_TIMEZONES;
  }
};

const Settings: React.FC = () => {
  const { t } = useI18n();
  const qc = useQueryClient();

  const { data: settings, isLoading, error } = useQuery({ queryKey: ['settings'], queryFn: getSettings });
  const { data: appInfo } = useQuery({ queryKey: ['app-info'], queryFn: getAppInfo });

  const [language, setLanguage] = useState('ja');
  const [timezone, setTimezone] = useState('Asia/Tokyo');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!settings) return;
    setLanguage(settings.language);
    setTimezone(settings.timezone);
  }, [settings]);

  const zones = useMemo(timezoneOptions, []);

  const save = useMutation({
    mutationFn: () => updateSettings({ language, timezone }),
    onSuccess: () => {
      setSaved(true);
      qc.invalidateQueries({ queryKey: ['settings'] });
    },
  });

  if (isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>;
  if (error) return <Alert severity="error">{t('common.loadError')}</Alert>;

  const dirty = settings != null && (language !== settings.language || timezone !== settings.timezone);

  const infoRows: { label: string; value: string | undefined }[] = [
    { label: t('settings.version'), value: appInfo?.version },
    { label: t('settings.gitHash'), value: appInfo?.git_sha },
    { label: t('settings.buildTime'), value: appInfo?.build_time },
    { label: t('settings.environment'), value: appInfo?.environment },
  ];

  return (
    <Box sx={{ maxWidth: 640, display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <Box sx={card}>
        <Box sx={sectionHeader}>{t('settings.display')}</Box>
        <Box sx={{ p: '18px', display: 'flex', flexDirection: 'column', gap: '18px' }}>
          <TextField
            select
            label={t('settings.language')}
            value={language}
            onChange={(e) => { setLanguage(e.target.value); setSaved(false); }}
            sx={{ maxWidth: 280 }}
          >
            <MenuItem value="ja">{t('settings.language.ja')}</MenuItem>
            <MenuItem value="en">{t('settings.language.en')}</MenuItem>
          </TextField>
          <Autocomplete
            options={zones}
            value={timezone}
            onChange={(_, v) => { if (v) { setTimezone(v); setSaved(false); } }}
            disableClearable
            sx={{ maxWidth: 360 }}
            renderInput={(params) => (
              <TextField {...params} label={t('settings.timezone')} helperText={t('settings.timezoneHelp')} />
            )}
          />
          <Box sx={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Button
              variant="contained"
              disabled={!dirty || save.isPending}
              onClick={() => save.mutate()}
              sx={{ px: '24px' }}
            >
              {t('settings.save')}
            </Button>
            {saved && !dirty && <Box sx={{ fontSize: 13, color: ds.success }}>{t('settings.saved')}</Box>}
            {save.isError && <Box sx={{ fontSize: 13, color: ds.dangerText }}>{t('settings.saveError')}</Box>}
          </Box>
        </Box>
      </Box>

      <Box sx={card}>
        <Box sx={sectionHeader}>{t('settings.appInfo')}</Box>
        <Box sx={{ p: '6px 0' }}>
          {infoRows.map((row) => (
            <Box key={row.label} sx={{ display: 'flex', px: '18px', py: '9px', gap: '16px' }}>
              <Box sx={{ width: 130, flexShrink: 0, fontSize: 13, color: ds.textSub }}>{row.label}</Box>
              <Box sx={{ fontSize: 13, color: ds.text, fontFamily: 'ui-monospace, monospace', wordBreak: 'break-all' }}>
                {row.value ?? '—'}
              </Box>
            </Box>
          ))}
        </Box>
      </Box>
    </Box>
  );
};

export default Settings;
