import { AppBar, Box, Button, Container, CssBaseline, Toolbar, Typography } from "@mui/material";
import { Navigate, Route, Routes, Link as RouterLink } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import AdminActionsPage from "./pages/AdminActionsPage";
import AdminUsersPage from "./pages/AdminUsersPage";
import AdminJobsPage from "./pages/AdminJobsPage";
import { useAuth } from "./hooks/useAuth";

const ProtectedRoute = ({ children }: { children: JSX.Element }) => {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return children;
};

function App() {
  const { user, logout } = useAuth();

  return (
    <>
      <CssBaseline />
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            Building Control
          </Typography>
          {user && (
            <>
              <Button color="inherit" component={RouterLink} to="/">
                Dashboard
              </Button>
              {user.role === "admin" && (
                <>
                  <Button color="inherit" component={RouterLink} to="/admin/actions">
                    Actions
                  </Button>
                  <Button color="inherit" component={RouterLink} to="/admin/users">
                    Users
                  </Button>
                  <Button color="inherit" component={RouterLink} to="/admin/jobs">
                    Jobs
                  </Button>
                </>
              )}
              <Button color="inherit" onClick={logout}>
                Logout
              </Button>
            </>
          )}
        </Toolbar>
      </AppBar>
      <Container sx={{ py: 3 }}>
        <Box>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <DashboardPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin/actions"
              element={
                <ProtectedRoute>
                  <AdminActionsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin/users"
              element={
                <ProtectedRoute>
                  <AdminUsersPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin/jobs"
              element={
                <ProtectedRoute>
                  <AdminJobsPage />
                </ProtectedRoute>
              }
            />
          </Routes>
        </Box>
      </Container>
    </>
  );
}

export default App;
