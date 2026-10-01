import { Box } from '@mui/material';
import { HOUR_LINE_CENTER_OFFSET, hourLabelMinutes } from '../../calendar/weekLayout';
import { formatMinute } from '../../calendar/zonedTime';

interface HourLabelsProps {
  /** 文字の色 */
  color: string;
  /** 左の余白（px） */
  paddingLeft: number;
}

/**
 * 時間グリッドの時刻列（週表示・「今日」の 1 日・締めの格子で共通）。
 * 文字の縦の真ん中を正時の線に合わせる（Google カレンダーと同じ。ADR-0023）。0:00 は上で切れるので出さない。
 * 置く先の列は 1 分 = 1px の高さを持ち、`position: relative` であること。
 */
export default function HourLabels({ color, paddingLeft }: HourLabelsProps) {
  return (
    <>
      {hourLabelMinutes().map((minute) => (
        <Box
          key={minute}
          data-hour-label={minute / 60}
          sx={{
            position: 'absolute', left: 0, right: 0, top: minute + HOUR_LINE_CENTER_OFFSET, transform: 'translateY(-50%)',
            fontSize: 10, lineHeight: 1, pl: `${paddingLeft}px`, color, whiteSpace: 'nowrap', pointerEvents: 'none',
          }}
        >
          {formatMinute(minute)}
        </Box>
      ))}
    </>
  );
}
