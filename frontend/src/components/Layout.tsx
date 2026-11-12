import React, { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Box, Button, Chip, Drawer, IconButton, ListItemText, Menu, MenuItem, useMediaQuery } from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import { ds, headingFont } from '../theme';
import { useI18n } from '../i18n';
import { useAuth } from '../auth/AuthProvider';
import AppMark from './AppMark';
import OfflineNotice from './OfflineNotice';
import ProjectScopeSelect from './ProjectScopeSelect';
import { useProjectScope } from '../projects/useProjectScope';
import { BELOW_UPDATE_BAR } from '../pwa/updateBarHeight';
import type { TranslationKey } from '../i18n/translations';
import {
  CheckListIcon, BarsIcon, InboxIcon, PlusIcon, SlidersIcon, FolderIcon, FlagIcon, GridIcon, TreeIcon,
} from './icons';

const SIDEBAR_WIDTH = 224;
const TOPBAR_HEIGHT = 58;

const navItems: { labelKey: TranslationKey; path: string; icon: React.FC<{ size?: number; strokeWidth?: number }> }[] = [
  { labelKey: 'nav.tasks', path: '/tasks', icon: CheckListIcon },
  { labelKey: 'nav.gantt', path: '/gantt', icon: BarsIcon },
  { labelKey: 'nav.actuals', path: '/actuals', icon: GridIcon },
  { labelKey: 'nav.inbox', path: '/inbox', icon: InboxIcon },
  { labelKey: 'nav.projects', path: '/projects', icon: TreeIcon },
  { labelKey: 'nav.categories', path: '/categories', icon: FolderIcon },
  { labelKey: 'nav.milestones', path: '/milestones', icon: FlagIcon },
  { labelKey: 'nav.settings', path: '/settings', icon: SlidersIcon },
];

const pageTitles: { pattern: RegExp; titleKey: TranslationKey }[] = [
  { pattern: /^\/tasks\/new$/, titleKey: 'title.taskNew' },
  { pattern: /^\/tasks\/\d+$/, titleKey: 'title.taskEdit' },
  { pattern: /^\/tasks$/, titleKey: 'nav.tasks' },
  { pattern: /^\/gantt$/, titleKey: 'nav.gantt' },
  { pattern: /^\/actuals(\/\w+)?$/, titleKey: 'nav.actuals' },
  { pattern: /^\/inbox$/, titleKey: 'nav.inbox' },
  { pattern: /^\/projects$/, titleKey: 'nav.projects' },
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
        <AppMark size={30} />
        <Box sx={{ fontFamily: headingFont, fontSize: 15, fontWeight: 900, color: ds.text }}>{t('app.name')}</Box>
      </Box>
      {/* Displayed project (task #187). Tasks, Gantt, calendar due dates, actuals and milestones follow it */}
      <ProjectScopeSelect />
      <Box sx={{ pt: '4px', flex: 1, overflowY: 'auto' }}>
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

/** Account at the top right. Logs out from here when SSO is enabled. */
const AccountButton: React.FC = () => {
  const { user, ssoEnabled, signOut } = useAuth();
  const { t } = useI18n();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);

  const initial = (user?.display_name ?? 'W').trim().charAt(0).toUpperCase();
  const avatar = (
    <Box sx={{
      width: 34, height: 34, borderRadius: '50%', bgcolor: ds.primary, color: '#fff',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 14, fontWeight: 700, flexShrink: 0,
    }}>
      {initial}
    </Box>
  );

  // Deployments without SSO have no logout destination, so show it as decoration only
  if (!ssoEnabled) return avatar;

  return (
    <>
      <IconButton onClick={(e) => setAnchorEl(e.currentTarget)} sx={{ p: 0 }} aria-label={user?.display_name}>
        {avatar}
      </IconButton>
      <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
        <MenuItem disabled sx={{ opacity: '1 !important' }}>
          <ListItemText
            primary={user?.display_name}
            secondary={user?.email}
            slotProps={{
              primary: { sx: { fontSize: 14, fontWeight: 600 } },
              secondary: { sx: { fontSize: 12 } },
            }}
          />
        </MenuItem>
        <MenuItem onClick={() => { setAnchorEl(null); void signOut(); }} sx={{ fontSize: 14 }}>
          {t('account.signOut')}
        </MenuItem>
      </Menu>
    </>
  );
};

/** Screens that follow the project filter (the filter indicator is shown on them. task #187) */
const SCOPED_PATHS = /^\/(tasks|gantt|actuals|milestones)(\/|$)/;

/** Filter indicator. Clearing it goes back to all. */
const ScopeBadge: React.FC = () => {
  const { t } = useI18n();
  const location = useLocation();
  const { scope, setScope, projects } = useProjectScope();
  if (scope === 'all' || !SCOPED_PATHS.test(location.pathname) || /^\/tasks\/(new|\d+)$/.test(location.pathname)) {
    return null;
  }
  const name = scope === 'none' ? t('scope.none') : projects.find((p) => p.id === scope)?.path;
  if (name === undefined) return null;
  return (
    <Chip
      size="small"
      label={t('scope.badge', { name })}
      onDelete={() => setScope('all')}
      title={t('scope.clear')}
      sx={{
        // Shrinks on phone widths (fits in 390px. task #639)
        maxWidth: { xs: 140, sm: 320 }, minWidth: 0, flexShrink: 1, bgcolor: ds.primaryPale, color: ds.primary, fontWeight: 600,
        '& .MuiChip-label': { overflow: 'hidden', textOverflow: 'ellipsis' },
      }}
    />
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
            // While the new-version bar is shown, sit right below it (ADR-0072)
            position: 'sticky', top: BELOW_UPDATE_BAR, height: `calc(100svh - ${BELOW_UPDATE_BAR})`,
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
            display: 'flex', alignItems: 'center', gap: { xs: 1, sm: 2 }, px: { xs: '8px', sm: '20px' },
            // While the new-version bar is shown, sit right below it (ADR-0072)
            position: 'sticky', top: BELOW_UPDATE_BAR, zIndex: 10,
          }}
        >
          {!isDesktop && (
            <IconButton edge="start" onClick={() => setMobileOpen(true)} sx={{ color: ds.text }}>
              <MenuIcon />
            </IconButton>
          )}
          {/* No title on phone widths (the left menu shows where you are) */}
          <Box sx={{
            display: { xs: 'none', sm: 'block' },
            fontFamily: headingFont, fontSize: 16, fontWeight: 700, color: ds.text, whiteSpace: 'nowrap',
            overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0,
          }}>
            {title}
          </Box>
          <ScopeBadge />
          <Box sx={{ flex: 1 }} />
          {isDesktop ? (
            <Button
              variant="contained"
              onClick={() => navigate('/tasks/new')}
              startIcon={<PlusIcon size={16} />}
              sx={{ px: '18px', py: '7px', whiteSpace: 'nowrap' }}
            >
              {t('action.newTask')}
            </Button>
          ) : (
            <IconButton
              onClick={() => navigate('/tasks/new')}
              aria-label={t('action.newTask')}
              sx={{ color: ds.primary, flexShrink: 0 }}
            >
              <PlusIcon size={20} />
            </IconButton>
          )}
          <AccountButton />
        </Box>

        <Box component="main" sx={{ flex: 1, p: { xs: '16px', md: '24px' } }}>
          {/* Offline (task #192 / ADR-0028). The shell is shown but data can't be loaded */}
          <OfflineNotice />
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
};

export default Layout;
