import React, { useMemo } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import "../styles/RecommendationResult.css";

type QuizState = {
  name: string;
  mood: string;
  space: string;
  intensity?: string;
  notes?: string[];
  season?: string;
  occasion?: string;
};

function isQuizState(value: unknown): value is QuizState {
  if (!value || typeof value !== "object") {
    return false;
  }

  const data = value as Record<string, unknown>;

  return (
    typeof data.name === "string" &&
    typeof data.mood === "string" &&
    typeof data.space === "string"
  );
}

type RecommendationContent = {
  title: string;
  scent: string;
  description: string;
  salesNote: string;
};

const RecommendationResult: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();

  const data = isQuizState(location.state) ? location.state : null;

  const recommendation = useMemo<RecommendationContent | null>(() => {
    if (!data) {
      return null;
    }

    const mood = data.mood.toLowerCase();
    const space = data.space.toLowerCase();

    if (mood.includes("cozy")) {
      return {
        title: "Soft warmth with a comforting glow",
        scent: "Warm vanilla, soft woods, and a smooth amber finish.",
        description:
          "This profile feels calm, inviting, and easy to live with — perfect for evenings, unwinding, and creating a home that feels warm and welcoming.",
        salesNote:
          "A beautiful choice if you want a candle that feels safe, elegant, and instantly giftable.",
      };
    }

    if (mood.includes("fresh")) {
      return {
        title: "Clean, airy, and naturally uplifting",
        scent: "Bright citrus, fresh linen, and soft clean notes.",
        description:
          "This direction works beautifully when you want your space to feel lighter, polished, and effortlessly refreshed.",
        salesNote:
          "Ideal for everyday use if you love candles that make a room feel open and elevated.",
      };
    }

    if (mood.includes("romantic")) {
      return {
        title: "Elegant, intimate, and softly luxurious",
        scent: "Rose, warm amber, and a velvety floral glow.",
        description:
          "This profile feels graceful and refined, with enough softness to create a more intimate atmosphere.",
        salesNote:
          "A strong pick for gifting, special evenings, or making your bedroom feel more luxurious.",
      };
    }

    if (mood.includes("focus")) {
      return {
        title: "Grounded and quietly refined",
        scent: "Sandalwood, tea, and calm woody balance.",
        description:
          "This style feels clean, stable, and composed — ideal for slow mornings, reading, or work sessions that need a calm atmosphere.",
        salesNote:
          "A smart choice if you want a candle that feels polished without becoming distracting.",
      };
    }

    if (space.includes("bathroom")) {
      return {
        title: "Fresh spa-like clarity",
        scent: "Airy florals, soft citrus, and a clean finish.",
        description:
          "This type of profile works especially well in smaller spaces where freshness and lightness matter most.",
        salesNote:
          "Perfect if you want your home to feel a little more like a boutique hotel or spa.",
      };
    }

    return {
      title: "Playful warmth with a little energy",
      scent: "Berries, spice, and a lively sweet finish.",
      description:
        "This recommendation feels expressive, memorable, and full of personality — something that adds mood the moment it’s lit.",
      salesNote:
        "A great match if you want a candle that stands out and makes the room feel instantly more alive.",
    };
  }, [data]);

  if (!data || !recommendation) {
    return (
      <main className="rr" aria-labelledby="rr-empty-title">
        <div className="rr__layout">
          <section className="rr__card rr__card--empty">
            <h1 id="rr-empty-title" className="rr__title">
              No result yet
            </h1>

            <p className="rr__text">
              Please take the quiz first so we can prepare your candle match.
            </p>

            <button
              type="button"
              className="rr__btn rr__btn--primary"
              onClick={() => navigate("/recommendation-quiz")}
            >
              Start the quiz
            </button>
          </section>
        </div>
      </main>
    );
  }

  const notesText =
    Array.isArray(data.notes) && data.notes.length > 0
      ? data.notes.join(", ")
      : "Selected scent notes";

  return (
    <main className="rr" aria-labelledby="rr-title">
      <div className="rr__layout">
        <header className="rr__header">
          <p className="rr__eyebrow">Your curated candle profile</p>

          <h1 id="rr-title" className="rr__title">
            {data.name}, here’s the candle direction that suits you best
          </h1>

          <p className="rr__subtitle">
            Based on your answers, this is the scent profile most likely to feel
            natural, beautiful, and worth bringing into your space.
          </p>
        </header>

        <section className="rr__card" aria-label="Recommendation result">
          <div className="rr__badge">Recommended vibe</div>

          <h2 className="rr__recommendationTitle">{recommendation.title}</h2>

          <p className="rr__recommendation">{recommendation.scent}</p>

          <p className="rr__description">{recommendation.description}</p>

          <dl className="rr__summary" aria-label="Your quiz summary">
            <div className="rr__summaryRow">
              <dt className="rr__summaryLabel">Mood</dt>
              <dd className="rr__summaryValue">{data.mood}</dd>
            </div>

            <div className="rr__summaryRow">
              <dt className="rr__summaryLabel">Space</dt>
              <dd className="rr__summaryValue">{data.space}</dd>
            </div>

            {data.intensity ? (
              <div className="rr__summaryRow">
                <dt className="rr__summaryLabel">Intensity</dt>
                <dd className="rr__summaryValue">{data.intensity}</dd>
              </div>
            ) : null}

            <div className="rr__summaryRow">
              <dt className="rr__summaryLabel">Notes</dt>
              <dd className="rr__summaryValue">{notesText}</dd>
            </div>

            {data.season ? (
              <div className="rr__summaryRow">
                <dt className="rr__summaryLabel">Season</dt>
                <dd className="rr__summaryValue">{data.season}</dd>
              </div>
            ) : null}

            {data.occasion ? (
              <div className="rr__summaryRow">
                <dt className="rr__summaryLabel">Occasion</dt>
                <dd className="rr__summaryValue">{data.occasion}</dd>
              </div>
            ) : null}
          </dl>

          <div className="rr__callout">{recommendation.salesNote}</div>

          <div className="rr__actions">
            <Link className="rr__btn rr__btn--secondary" to="/recommendation-quiz">
              Retake quiz
            </Link>

            <Link className="rr__btn rr__btn--primary" to="/catalog">
              Shop matching candles
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
};

export default RecommendationResult;