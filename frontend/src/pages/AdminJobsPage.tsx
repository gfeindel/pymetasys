import {
  Alert,
  Box,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Typography,
  Button,
} from "@mui/material";
import { useState } from "react";
import { useJobs } from "../api/hooks";

const StatusChip = ({ status }: { status: string }) => {
  const color =
    status === "succeeded" ? "success" : status === "failed" || status === "timeout" ? "error" : "warning";
  return <Chip label={status} color={color as any} size="small" />;
};

const AdminJobsPage = () => {
  const [statusFilter, setStatusFilter] = useState<string>("");
  const { data: jobs, refetch, isFetching } = useJobs(statusFilter || undefined);

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: 2, display: "flex", gap: 2, alignItems: "center" }}>
        <FormControl sx={{ minWidth: 160 }}>
          <InputLabel id="status-filter-label">Status</InputLabel>
          <Select
            labelId="status-filter-label"
            label="Status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            size="small"
          >
            <MenuItem value="">All</MenuItem>
            <MenuItem value="queued">Queued</MenuItem>
            <MenuItem value="running">Running</MenuItem>
            <MenuItem value="succeeded">Succeeded</MenuItem>
            <MenuItem value="failed">Failed</MenuItem>
            <MenuItem value="timeout">Timeout</MenuItem>
          </Select>
        </FormControl>
        <Button variant="outlined" onClick={() => refetch()} disabled={isFetching}>
          Refresh
        </Button>
      </Paper>

      <Stack spacing={1}>
        {jobs?.map((job) => (
          <Paper key={job.id} sx={{ p: 2 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <StatusChip status={job.status} />
              <Typography variant="subtitle1">
                Job #{job.id} {job.action_name ? `– ${job.action_name}` : ""}
              </Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              Requested by: {job.requested_by_email || job.requested_by_user_id} · Created{" "}
              {new Date(job.created_at).toLocaleString()}
            </Typography>
            {job.parsed_result && (
              <Typography variant="body2" sx={{ mt: 0.5 }}>
                Parsed result: {job.parsed_result}
              </Typography>
            )}
            {job.error_message && (
              <Alert severity="error" sx={{ mt: 1 }}>
                {job.error_message}
              </Alert>
            )}
            {job.raw_response && (
              <Box sx={{ mt: 1 }}>
                <Typography variant="caption" color="text.secondary">
                  Raw response
                </Typography>
                <Paper
                  variant="outlined"
                  sx={{ p: 1, mt: 0.5, maxHeight: 200, overflow: "auto", whiteSpace: "pre-wrap", fontFamily: "monospace" }}
                >
                  {job.raw_response}
                </Paper>
              </Box>
            )}
          </Paper>
        ))}
      </Stack>
    </Stack>
  );
};

export default AdminJobsPage;
