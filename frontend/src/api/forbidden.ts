import { isAxiosError } from 'axios';

/** Whether refused for not being an admin (403). Moving to another tree requires admin on both source and destination (ADR-0066). */
export const isForbidden = (error: unknown): boolean =>
  isAxiosError(error) && error.response?.status === 403;
