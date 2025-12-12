import {
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  Grid,
  Paper,
  Stack,
  TextField,
  Typography,
  Alert,
} from "@mui/material";
import { useState } from "react";
import { useActions, useCreateAction, useTestRegex } from "../api/hooks";

const AdminActionsPage = () => {
  const { data: actions } = useActions();
  const createAction = useCreateAction();
  const testRegex = useTestRegex();
  const [form, setForm] = useState({
    name: "",
    slug: "",
    description: "",
    input_sequence: "",
    result_regex: "",
    timeout_seconds: 3,
    is_enabled: true,
  });
  const [message, setMessage] = useState<string | null>(null);
  const [sampleText, setSampleText] = useState("");
  const [regexResult, setRegexResult] = useState<{ matches: string[]; groups: Record<string, any> } | null>(null);
  const [regexError, setRegexError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    try {
      await createAction.mutateAsync(form);
      setMessage("Action created");
      setForm({ ...form, name: "", slug: "", description: "", input_sequence: "", result_regex: "" });
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || "Error creating action");
    }
  };

  return (
    <Grid container spacing={3}>
      <Grid item xs={12} md={5}>
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" gutterBottom>
            Create Action
          </Typography>
          {message && (
            <Alert severity="info" sx={{ mb: 1 }}>
              {message}
            </Alert>
          )}
          <Box component="form" onSubmit={handleSubmit} display="flex" flexDirection="column" gap={2}>
            <TextField label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <TextField label="Slug" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} />
            <TextField
              label="Description"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
            <TextField
              label="Input Sequence"
              value={form.input_sequence}
              onChange={(e) => setForm({ ...form, input_sequence: e.target.value })}
              multiline
              minRows={3}
              helperText="Use literal characters; special keys like <TAB> or <ESC> can be encoded literally."
            />
            <TextField
              label="Result Regex"
              value={form.result_regex}
              onChange={(e) => setForm({ ...form, result_regex: e.target.value })}
              multiline
              minRows={2}
            />
            <TextField
              label="Timeout (seconds)"
              type="number"
              value={form.timeout_seconds}
              onChange={(e) => setForm({ ...form, timeout_seconds: Number(e.target.value) })}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.is_enabled}
                  onChange={(e) => setForm({ ...form, is_enabled: e.target.checked })}
                />
              }
              label="Enabled"
            />
            <Button type="submit" variant="contained">
              Save
            </Button>
            <Typography variant="subtitle2" sx={{ mt: 1 }}>
              Quick Regex Test
            </Typography>
            <TextField
              label="Sample Text"
              value={sampleText}
              onChange={(e) => setSampleText(e.target.value)}
              multiline
              minRows={3}
            />
            <Button
              variant="outlined"
              onClick={async () => {
                setRegexError(null);
                setRegexResult(null);
                try {
                  const res = await testRegex.mutateAsync({ sample_text: sampleText, regex: form.result_regex });
                  setRegexResult(res);
                } catch (err: any) {
                  setRegexError(err?.response?.data?.detail || "Regex test failed");
                }
              }}
            >
              Test Regex
            </Button>
            {regexError && (
              <Alert severity="error" sx={{ mt: 1 }}>
                {regexError}
              </Alert>
            )}
            {regexResult && (
              <Alert severity="success" sx={{ mt: 1 }}>
                Matches: {regexResult.matches.join(", ") || "none"}; Groups: {JSON.stringify(regexResult.groups)}
              </Alert>
            )}
          </Box>
        </Paper>
      </Grid>
      <Grid item xs={12} md={7}>
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" gutterBottom>
            Actions
          </Typography>
          <Stack spacing={1}>
            {actions?.map((a) => (
              <Paper key={a.id} sx={{ p: 2 }}>
                <Typography variant="subtitle1">
                  {a.name} ({a.slug})
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {a.description}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Enabled: {a.is_enabled ? "yes" : "no"} | Updated: {new Date(a.updated_at).toLocaleString()}
                </Typography>
              </Paper>
            ))}
          </Stack>
        </Paper>
      </Grid>
    </Grid>
  );
};

export default AdminActionsPage;
