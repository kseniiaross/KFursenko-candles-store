export type OrderItem = {
  id: number;
  candle_id: number;
  candle_name: string;
  unit_price: string;
  quantity: number;
};

export type Order = {
  id: number;
  status: string;
  currency: string;
  total_amount: string;
  stripe_payment_intent_id: string;
  items: OrderItem[];
  created_at: string;
};

export type CartItem = {
  id: number;
  candle_id: number;
  candle_name?: string;
  quantity: number;
  unit_price?: string;
};

export type Cart = {
  id?: number;
  items: CartItem[];
  total_amount?: string;
};