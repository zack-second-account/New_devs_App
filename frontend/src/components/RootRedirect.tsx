import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext.new';

export default function RootRedirect() {
  const auth = useAuth();
  const { user } = auth;
  // - auth.status does not exist on the context, so this was always false and never waited for the stored session
  // - on refresh the first render has no user yet, which bounced a logged-in user to /login
  const loading = auth.isLoading;

  // Show loading state while checking auth
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  // If user is authenticated, redirect to dashboard
  if (user) {
    return <Navigate to="/dashboard" replace />;
  }

  // If not authenticated, redirect to login
  return <Navigate to="/login" replace />;
}
