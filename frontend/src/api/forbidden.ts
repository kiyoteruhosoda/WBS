import { isAxiosError } from 'axios';

/** 管理者でないため断られた（403）か。別の木へ移す操作は、元と先の両方の管理者だけ（ADR-0066）。 */
export const isForbidden = (error: unknown): boolean =>
  isAxiosError(error) && error.response?.status === 403;
