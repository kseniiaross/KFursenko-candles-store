export type CartItem = {
  id: number;

  candle: {
    id: number;
    name: string;
    price: string;
    slug: string;
    in_stock: boolean;
  };

  quantity: number;
};

export type Cart = {
  id: number;
  items: CartItem[];
};