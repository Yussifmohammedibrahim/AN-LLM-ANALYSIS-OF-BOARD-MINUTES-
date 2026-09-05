import React, { useContext, useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import AuthContext from '../context/AuthContext';
import LoadingSpinner from './LoadingSpinner';
import LandingPage from './LandingPage';

const AuthAwareHome = () => {
  const { loading, isAuthenticated } = useContext(AuthContext);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    if (!loading) {
      setAuthChecked(true);
    }
  }, [loading]);

  if (loading || !authChecked) {
    return <LoadingSpinner />;
  }

  if (isAuthenticated()) {
    return <Navigate to="/dashboard" replace />;
  }

  return <LandingPage />;
};

export default AuthAwareHome;

