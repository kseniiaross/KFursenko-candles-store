// frontend/src/types/content.ts
export type AboutGalleryItem = {
  id: number;
  title: string;
  slug: string;
  media_type: "image" | "video";
  media: string;
  preview_image: string | null;
  caption: string;
  sort_order: number;
  is_active: boolean;
  created_at: string;
};

export type AboutReviewItem = {
  id: number;
  title: string;
  customer_name: string;
  image: string;
  caption: string;
  sort_order: number;
  is_active: boolean;
  created_at: string;
};