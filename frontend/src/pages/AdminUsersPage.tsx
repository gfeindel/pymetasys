import { Alert, Box, Button, Paper, Stack, TextField, Typography, MenuItem } from "@mui/material";
import { useState } from "react";
import { useCreateUser, useUsers } from "../api/hooks";

const AdminUsersPage = () => {
  const { data: users } = useUsers();
  const createUser = useCreateUser();
  const [form, setForm] = useState({ email: "", password: "", role: "user" });
  const [message, setMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    try {
      await createUser.mutateAsync(form);
      setMessage("User created");
      setForm({ email: "", password: "", role: "user" });
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || "Error creating user");
    }
  };

  return (
    <Stack spacing={3}>
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom>
          Create User
        </Typography>
        {message && (
          <Alert severity="info" sx={{ mb: 1 }}>
            {message}
          </Alert>
        )}
        <Box component="form" onSubmit={handleSubmit} display="flex" flexDirection="column" gap={2}>
          <TextField label="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <TextField
            label="Password"
            type="password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
          <TextField
            select
            label="Role"
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
          >
            <MenuItem value="user">User</MenuItem>
            <MenuItem value="admin">Admin</MenuItem>
          </TextField>
          <Button type="submit" variant="contained">
            Save
          </Button>
        </Box>
      </Paper>
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom>
          Users
        </Typography>
        <Stack spacing={1}>
          {users?.map((u) => (
            <Paper key={u.id} sx={{ p: 2 }}>
              <Typography variant="subtitle1">{u.email}</Typography>
              <Typography variant="body2" color="text.secondary">
                Role: {u.role} | Created: {new Date(u.created_at).toLocaleString()}
              </Typography>
            </Paper>
          ))}
        </Stack>
      </Paper>
    </Stack>
  );
};

export default AdminUsersPage;
