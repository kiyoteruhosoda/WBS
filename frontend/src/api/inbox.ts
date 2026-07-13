import client from './client';
import type { InboxItem, Task } from '../types';

export const getInbox = async (): Promise<InboxItem[]> => {
  const { data } = await client.get('/inbox');
  return data;
};

export const createInboxItem = async (payload: { title: string; memo?: string }): Promise<InboxItem> => {
  const { data } = await client.post('/inbox', payload);
  return data;
};

export const convertInboxItem = async (id: number, taskPayload: Partial<Task>): Promise<Task> => {
  const { data } = await client.post(`/inbox/${id}/convert`, taskPayload);
  return data;
};

export const deleteInboxItem = async (id: number): Promise<void> => {
  await client.delete(`/inbox/${id}`);
};
