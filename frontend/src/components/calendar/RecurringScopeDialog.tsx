import React, { useState } from 'react';
import {
  Button, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, Radio, RadioGroup,
} from '@mui/material';
import { useI18n } from '../../i18n';
import type { RecurringScope } from '../../calendar/eventForm';

interface Props {
  open: boolean;
  /** 直す範囲か、消す範囲か（文言が変わる） */
  purpose: 'edit' | 'delete';
  onCancel: () => void;
  onChoose: (scope: RecurringScope) => void;
}

/** 繰り返し予定の範囲を聞く（移植元 `ShowRecurringScopeDialogAsync` / `ShowRecurringDeleteScopeDialogAsync`）。 */
const RecurringScopeDialog: React.FC<Props> = ({ open, purpose, onCancel, onChoose }) => {
  const { t } = useI18n();
  const [scope, setScope] = useState<RecurringScope>('this');
  const labels: Record<RecurringScope, string> = purpose === 'edit'
    ? { this: t('calendar.scopeEditThis'), following: t('calendar.scopeEditFollowing'), all: t('calendar.scopeEditAll') }
    : { this: t('calendar.scopeDeleteThis'), following: t('calendar.scopeDeleteFollowing'), all: t('calendar.scopeDeleteAll') };

  // 次に開いたときは「この予定のみ」から（移植元の既定）。
  const cancel = () => { setScope('this'); onCancel(); };
  const choose = () => { setScope('this'); onChoose(scope); };

  return (
    <Dialog open={open} onClose={cancel} maxWidth="xs" fullWidth>
      <DialogTitle>{t(purpose === 'edit' ? 'calendar.scopeEditTitle' : 'calendar.scopeDeleteTitle')}</DialogTitle>
      <DialogContent>
        <RadioGroup value={scope} onChange={(e) => setScope(e.target.value as RecurringScope)}>
          {(['this', 'following', 'all'] as const).map((s) => (
            <FormControlLabel key={s} value={s} control={<Radio />} label={labels[s]} data-testid={`scope-${s}`} />
          ))}
        </RadioGroup>
      </DialogContent>
      <DialogActions>
        <Button onClick={cancel}>{t('calendar.cancel')}</Button>
        <Button
          variant="contained"
          color={purpose === 'delete' ? 'error' : 'primary'}
          onClick={choose}
        >
          {t('calendar.ok')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default RecurringScopeDialog;
