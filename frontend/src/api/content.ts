import api from "../api/axiosInstance";
import type { AboutGalleryItem, AboutReviewItem } from "../types/content";

export async function listAboutGallery(): Promise<AboutGalleryItem[]> {
  // /candles/about-gallery/ no longer exists on the backend — the
  // AboutGalleryItem model was replaced by the unified GalleryItem model,
  // served from /candles/gallery/ and filtered by content_type.
  const response = await api.get<AboutGalleryItem[]>("/candles/gallery/", {
    params: { content_type: "gallery" },
  });
  return Array.isArray(response.data) ? response.data : [];
}

export async function listAboutReviews(): Promise<AboutReviewItem[]> {
  const response = await api.get<AboutReviewItem[]>("/candles/about-reviews/");
  return Array.isArray(response.data) ? response.data : [];
}