import React from 'react';
import { Box } from '@mui/material';
import { categoryColor } from '../theme';
import type { Category } from '../types';

interface Props {
  categoryId: number | null | undefined;
  categories?: Category[];
  size?: number;
}

const CategoryDot: React.FC<Props> = ({ categoryId, categories, size = 8 }) => {
  const cat = categories?.find((c) => c.id === categoryId);
  return (
    <Box component="span" sx={{
      width: size, height: size, borderRadius: '50%', flexShrink: 0, display: 'inline-block',
      bgcolor: categoryColor(categoryId, cat?.color),
    }} />
  );
};

export default CategoryDot;
