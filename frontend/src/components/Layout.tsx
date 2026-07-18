import React, { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Box, Button, Drawer, IconButton, useMediaQuery } from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import { ds } from '../theme';
import {
  GridIcon, CheckListIcon, BarsIcon, CalendarIcon, InboxIcon,
  CheckIcon, PlusIcon, TodayIcon,
} from './icons';

const SIDEBAR_WIDTH = 224;
const TOPBAR_HEIGHT = 58;

const navItems = [
  { label: 'ダッシュボード', path: '/', icon: GridIcon },
  { label: '今日のタスク', path: '/today', icon: TodayIcon },
  { label: 'タスク', path: '/tasks', icon: CheckListIcon },
  { label: 'ガントチャート', path: '/gantt', icon: BarsIcon },
  { label: 'カレンダー', path: '/calendar', icon: CalendarIcon },
  { label: 'インボックス', path: '/inbox', icon: InboxIcon },
];

const pageTitles: { pattern: RegExp; title: string }[] = [
  { pattern: /^\/$/, title: 'ダッシュボード' },
  { pattern: /^\/today$/, title: '今日のタスク' },
  { pattern: /^\/tasks\/new$/, title: '新しいタスク' },
  { pattern: /^\/tasks\/\d+$/, title: 'タスクの編集' },
  { pattern: /^\/tasks$/, title: 'タスク' },
  { pattern: /^\/gantt$/, title: 'ガントチャート' },
  { pattern: /^\/calendar$/, title: 'カレンダー' },
  { pattern: /^\/inbox$/, title: 'インボックス' },
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
        <Box sx={{ fontSize: 15, fontWeight: 700, color: ds.text }}>タスク管理</Box>
      </Box>
      <Box sx={{ pt: '8px', flex: 1 }}>
        {navItems.map((item) => (
          <NavItem
            key={item.path}
            label={item.label}
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

  const title = pageTitles.find((p) => p.pattern.test(location.pathname))?.title ?? 'タスク管理';

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
            新規タスク
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
