import React from 'react';
import { IconButton, Tooltip } from '@mui/material';
import VolumeUpIcon from '@mui/icons-material/VolumeUp';
import VolumeOffIcon from '@mui/icons-material/VolumeOff';
import { useAlarmSoundSetting } from '../preferences/alarmSound';
import { useI18n } from '../i18n';
import { ds } from '../theme';

/** 予定の通知の音を消す・鳴らす（task #520、ADR-0052）。どの画面でも上部に出す。知らせの表示は消さない */
const AlarmSoundButton: React.FC = () => {
  const { t } = useI18n();
  const { sound, setSound } = useAlarmSoundSetting();
  const label = sound ? t('alarmSound.mute') : t('alarmSound.unmute');
  return (
    <Tooltip title={label}>
      <IconButton
        onClick={() => setSound(!sound)}
        aria-label={label}
        aria-pressed={!sound}
        sx={{ color: sound ? ds.textSub : ds.primary, flexShrink: 0 }}
      >
        {sound ? <VolumeUpIcon fontSize="small" /> : <VolumeOffIcon fontSize="small" />}
      </IconButton>
    </Tooltip>
  );
};

export default AlarmSoundButton;
