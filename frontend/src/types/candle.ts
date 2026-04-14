export interface CollectionParent {
  id: number
  name: string
  slug: string
}

export interface CollectionChild {
  id: number
  name: string
  slug: string
}

export interface Collection {
  id: number
  name: string
  slug: string
  is_group?: boolean
  parent?: CollectionParent | null
  children?: CollectionChild[]
}

export interface Category {
  id: number
  name: string
  slug: string
}

export type BadgeKind =
  | "new_shopper"
  | "loyalty"
  | "b1g2"
  | "holiday"
  | "discount"
  | string

export interface CandleBadge {
  slug: string
  badge_text: string
  kind: BadgeKind
  discount_percent?: number | null
  priority?: number
}

export interface CandleImage {
  id: number
  image: string
  sort_order: number
}

/* =========================
   VARIANT MODEL (NEW)
========================= */

export interface CandleVariant {
  id: number
  size: string
  price: string
  stock_qty: number
  is_active: boolean
}

/* =========================
   CANDLE MODEL
========================= */

export interface Candle {
  id: number
  name: string
  slug: string
  description: string

  image: string | null
  images?: CandleImage[]

  /* fallback price (optional now) */
  price?: string

  discount_price?: number | null

  stock_qty?: number
  in_stock?: boolean

  is_sold_out: boolean
  is_bestseller: boolean

  created_at: string

  category?: Category
  collections: Collection[]

  badges?: CandleBadge[]

  /* NEW */
  variants?: CandleVariant[]
}