import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { listAboutGallery } from "../api/content";
import type { AboutGalleryItem } from "../types/content";

import "../styles/Gallery.css";

const Gallery: React.FC = () => {
  const { t } = useTranslation();

  const [items, setItems] = useState<AboutGalleryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        const data = await listAboutGallery();
        if (!active) return;
        setItems(data);
      } catch {
        if (!active) return;
        setError(true);
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void load();

    return () => {
      active = false;
    };
  }, []);

  if (loading) return <div>{t("gallery.loading")}</div>;

  if (error) return <div>{t("gallery.loadError")}</div>;

  return (
    <main className="galleryPage">
      <h1>{t("gallery.title")}</h1>

      {items.length === 0 ? (
        <p>{t("gallery.empty")}</p>
      ) : (
        <div className="galleryGrid">
          {items.map((item, index) => {
            const reverse = index % 2 !== 0;

            return (
              <div
                key={item.id}
                className={`galleryCard ${reverse ? "reverse" : ""}`}
              >
                <div className="galleryCard__media">
                  {item.media_type === "video" ? (
                    <video
                      className="galleryCard__video"
                      controls
                      playsInline
                      muted
                      preload="metadata"
                    >
                      <source src={item.media} type="video/mp4" />
                    </video>
                  ) : (
                    <img
                      src={item.media}
                      alt={item.title}
                      className="galleryCard__image"
                    />
                  )}
                </div>

                <div className="galleryCard__body">
                  <h2>{item.title}</h2>
                  <p>{item.caption}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
};

export default Gallery;