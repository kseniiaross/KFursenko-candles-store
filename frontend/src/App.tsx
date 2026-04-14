import React, { useCallback, useEffect } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";

import Header from "./view/Header";
import Footer from "./view/Footer";
import SizeModal from "./components/SizeModal";
import Home from "./view/Home";
import Catalog from "./view/Catalog";
import CatalogDetail from "./view/CatalogDetail";
import Cart from "./view/Cart";
import Checkout from "./view/Checkout";
import PaymentSuccess from "./view/PaymentSuccess";
import PaymentCancel from "./view/PaymentCancel";
import Orders from "./view/Orders";

import LoginChoice from "./view/LoginChoice";
import Login from "./view/Login";
import Register from "./view/Register";

import StoryMission from "./view/StoryMission";
import Contacts from "./view/Contacts";
import Gallery from "./view/Gallery";
import Reviews from "./view/Reviews";

import RecommendationQuiz from "./view/RecommendationQuiz";
import RecommendationResult from "./view/RecommendationResult";

import LumiereWidget from "./view/LumiereWidget";

import Delivery from "./view/CustomerCare/Delivery";
import Payments from "./view/CustomerCare/Payments";
import Policy from "./view/CustomerCare/Policy";
import Profile from "./view/Profile";
import { clearAuthStorage, getAccessToken } from "./utils/token";
import { useAppDispatch, useAppSelector } from "./store/hooks";
import { logout, setUser } from "./store/authSlice";
import { useTheme } from "./theme/ThemeProvider";
import PrivateRoute from "./components/PrivateRoute";
import { getProfile } from "./services/auth";

import "./App.css";

const App: React.FC = () => {
  const dispatch = useAppDispatch();
  const location = useLocation();
  const { theme } = useTheme();

  const isLoggedIn = useAppSelector((state) => Boolean(state.auth?.isLoggedIn));

  const firstName = useAppSelector(
    (state) => (state.auth?.user?.first_name ?? null) as string | null
  );

  // При старте — если токен есть но user не загружен, загружаем профиль
  useEffect(() => {
    const token = getAccessToken();
    if (!token) return;
    if (firstName) return; // профиль уже есть

    getProfile(token)
      .then((user) => {
        dispatch(setUser(user));
      })
      .catch(() => {
        // токен протух — разлогиниваем
        clearAuthStorage();
        dispatch(logout());
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleLogout = useCallback(() => {
    clearAuthStorage();
    dispatch(logout());
  }, [dispatch]);

  const isHomePage = location.pathname === "/";

  return (
    <div
      className={`appShell ${
        isHomePage ? "appShell--home" : "appShell--inner"
      } appShell--${theme}`}
    >
      <Header
        firstName={firstName}
        isLoggedIn={isLoggedIn}
        onLogout={handleLogout}
      />

      <div className="appShell__body">
        <Routes>
          <Route
            path="/"
            element={<Home firstName={firstName} isLoggedIn={isLoggedIn} />}
          />
          <Route element={<PrivateRoute />}>
            <Route path="/profile" element={<Profile />} />
          </Route>
          <Route path="/catalog" element={<Catalog />} />
          <Route path="/catalog/:slug" element={<CatalogDetail />} />

          <Route path="/cart" element={<Cart />} />
          <Route path="/checkout" element={<Checkout />} />

          <Route path="/payment/success" element={<PaymentSuccess />} />
          <Route path="/payment/cancel" element={<PaymentCancel />} />

          <Route path="/orders" element={<Orders />} />

          <Route path="/login-choice" element={<LoginChoice />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />

          <Route path="/delivery" element={<Delivery />} />
          <Route path="/payments" element={<Payments />} />
          <Route path="/policy" element={<Policy />} />

          <Route path="/contacts" element={<Contacts />} />
          <Route path="/story-mission" element={<StoryMission />} />
          <Route path="/gallery" element={<Gallery />} />
          <Route path="/reviews" element={<Reviews />} />

          <Route
            path="/recommendation-quiz"
            element={<RecommendationQuiz />}
          />
          <Route
            path="/recommendation-result"
            element={<RecommendationResult />}
          />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>

        <SizeModal />
      </div>

      <Footer />
      <LumiereWidget />
    </div>
  );
};

export default App;