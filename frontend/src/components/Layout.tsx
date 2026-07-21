import React, { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Box, Button, Drawer, IconButton, useMediaQuery } from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import { ds } from '../theme';
import { useI18n } from '../i18n';
import type { TranslationKey } from '../i18n/translations';
import {
  GridIcon, CheckListIcon, BarsIcon, CalendarIcon, InboxIcon,
  CheckIcon, PlusIcon, TodayIcon, SlidersIcon, FolderIcon, FlagIcon,
} from './icons';

const SIDEBAR_WIDTH = 224;
const TOPBAR_HEIGHT = 58;

const navItems: { labelKey: TranslationKey; path: string; icon: React.FC<{ size?: number; strokeWidth?: number }> }[] = [
  { labelKey: 'nav.dashboard', path: '/', icon: GridIcon },
  { labelKey: 'nav.today', path: '/today', icon: TodayIcon },
  { labelKey: 'nav.tasks', path: '/tasks', icon: CheckListIcon },
  { labelKey: 'nav.gantt', path: '/gantt', icon: BarsIcon },
  { labelKey: 'nav.calendar', path: '/calendar', icon: CalendarIcon },
  { labelKey: 'nav.inbox', path: '/inbox', icon: InboxIcon },
  { labelKey: 'nav.categories', path: '/categories', icon: FolderIcon },
  { labelKey: 'nav.milestones', path: '/milestones', icon: FlagIcon },
  { labelKey: 'nav.settings', path: '/settings', icon: SlidersIcon },
];

const pageTitles: { pattern: RegExp; titleKey: TranslationKey }[] = [
  { pattern: /^\/$/, titleKey: 'nav.dashboard' },
  { pattern: /^\/today$/, titleKey: 'nav.today' },
  { pattern: /^\/tasks\/new$/, titleKey: 'title.taskNew' },
  { pattern: /^\/tasks\/\d+$/, titleKey: 'title.taskEdit' },
  { pattern: /^\/tasks$/, titleKey: 'nav.tasks' },
  { pattern: /^\/gantt$/, titleKey: 'nav.gantt' },
  { pattern: /^\/calendar$/, titleKey: 'nav.calendar' },
  { pattern: /^\/inbox$/, titleKey: 'nav.inbox' },
  { pattern: /^\/categories$/, titleKey: 'nav.categories' },
  { pattern: /^\/milestones$/, titleKey: 'nav.milestones' },
  { pattern: /^\/settings$/, titleKey: 'settings.title' },
];

const NavItem: React.FC<{
  label: string; active: boolean; icon: React.FC<{ size?: number; strokeWidth?: number }>;
  onClick: () => void;
}> = ({ label, active, icon: Icon, onClick }) => (
  <Box
    component="button"
    onClick={onClick}
    sx={{
      display: 'flex', alignItems: 'center', gap: '10px', width: `calc(100% - 24px)`,
      m: '2px 12px', p: '9px 14px', borderRadius: '8px', border: 'none', cursor: 'pointer',
      font: 'inherit', fontSize: 14, textAlign: 'left',
      bgcolor: active ? ds.primaryPale : 'transparent',
      color: active ? ds.primary : '#414141',
      fontWeight: active ? 700 : 500,
      '& svg': { color: active ? ds.primary : ds.textMuted, flexShrink: 0 },
      '&:hover': { bgcolor: active ? ds.primaryPale : ds.hairline },
    }}
  >
    <Icon size={20} strokeWidth={1.8} />
    {label}
  </Box>
);

const Sidebar: React.FC<{ onNavigate?: () => void }> = ({ onNavigate }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useI18n();
  const isActive = (path: string) =>
    path === '/' ? location.pathname === '/' : location.pathname.startsWith(path);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', bgcolor: ds.paper }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '10px', height: TOPBAR_HEIGHT, px: '18px', flexShrink: 0 }}>
        <Box sx={{
          width: 30, height: 30, borderRadius: '8px', bgcolor: ds.primary, color: '#fff',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <CheckIcon size={18} />
        </Box>
        <Box sx={{ fontSize: 15, fontWeight: 700, color: ds.text }}>{t('app.name')}</Box>
      </Box>
      <Box sx={{ pt: '8px', flex: 1 }}>
        {navItems.map((item) => (
          <NavItem
            key={item.path}
            label={t(item.labelKey)}
            icon={item.icon}
            active={isActive(item.path)}
            onClick={() => { navigate(item.path); onNavigate?.(); }}
          />
        ))}
      </Box>
    </Box>
  );
};

const Layout: React.FC = () => {
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const isDesktop = useMediaQuery('(min-width:1024px)');
  const { t } = useI18n();

  const titleKey = pageTitles.find((p) => p.pattern.test(location.pathname))?.titleKey;
  const title = titleKey ? t(titleKey) : t('app.name');

  return (
    <Box sx={{ display: 'flex', minHeight: '100svh', bgcolor: ds.canvas }}>
      {isDesktop ? (
        <Box
          component="nav"
          sx={{
            width: SIDEBAR_WIDTH, flexShrink: 0, borderRight: `1px solid ${ds.border}`,
            position: 'sticky', top: 0, height: '100svh',
          }}
        >
          <Sidebar />
        </Box>
      ) : (
        <Drawer open={mobileOpen} onClose={() => setMobileOpen(false)}
          sx={{ '& .MuiDrawer-paper': { width: SIDEBAR_WIDTH } }}>
          <Sidebar onNavigate={() => setMobileOpen(false)} />
        </Drawer>
      )}

      <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <Box
          component="header"
          sx={{
            height: TOPBAR_HEIGHT, flexShrink: 0, bgcolor: ds.paper,
            borderBottom: `1px solid ${ds.border}`,
            display: 'flex', alignItems: 'center', gap: 2, px: '20px',
            position: 'sticky', top: 0, zIndex: 10,
          }}
        >
          {!isDesktop && (
            <IconButton edge="start" onClick={() => setMobileOpen(true)} sx={{ color: ds.text }}>
              <MenuIcon />
            </IconButton>
          )}
          <Box sx={{ fontSize: 16, fontWeight: 700, color: ds.text, whiteSpace: 'nowrap' }}>{title}</Box>
          <Box sx={{ flex: 1 }} />
          <Button
            variant="contained"
            onClick={() => navigate('/tasks/new')}
            startIcon={<PlusIcon size={16} />}
            sx={{ px: '18px', py: '7px', whiteSpace: 'nowrap' }}
          >
            {t('action.newTask')}
          </Button>
          <Box sx={{
            width: 34, height: 34, borderRadius: '50%', bgcolor: ds.primary, color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 14, fontWeight: 700, flexShrink: 0,
          }}>
            W
          </Box>
        </Box>

        <Box component="main" sx={{ flex: 1, p: { xs: '16px', md: '24px' } }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
};

export default Layout;
