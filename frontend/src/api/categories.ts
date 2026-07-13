import client from './client';
import type { Category } from '../types';

export const getCategories = async (): Promise<Category[]> => {
  const { data } = await client.get('/categories');
  return data;
};

export const createCategory = async (payload: Partial<Category>): Promise<Category> => {
  const { data } = await client.post('/categories', payload);
  return data;
};

export const updateCategory = async (id: number, payload: Partial<Category>): Promise<Category> => {
  const { data } = await client.put(`/categories/${id}`, payload);
  return data;
};

export const deleteCategory = async (id: number): Promise<void> => {
  await client.delete(`/categories/${id}`);
};
