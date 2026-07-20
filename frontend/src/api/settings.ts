import client from './client';
import type { AppInfo, UserSettings } from '../types';

export const getSettings = async (): Promise<UserSettings> => {
  const { data } = await client.get('/settings');
  return data;
};

export const updateSettings = async (payload: Partial<UserSettings>): Promise<UserSettings> => {
  const { data } = await client.put('/settings', payload);
  return data;
};

export const getAppInfo = async (): Promise<AppInfo> => {
  const { data } = await client.get('/info');
  return data;
};
