import React, { useContext, useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import AuthContext from '../context/AuthContext';
import LoadingSpinner from './LoadingSpinner'; // Assume exists or create

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

  return <Navigate to="/login" replace />;
};

export default AuthAwareHome;

