import { Alert, Box, Button, Card, CardActions, CardContent, Grid, Typography, Chip, Stack } from "@mui/material";
import { useActions, useJobs, useRunAction } from "../api/hooks";
import { useAuth } from "../hooks/useAuth";

const StatusChip = ({ status }: { status: string }) => {
  const color =
    status === "succeeded" ? "success" : status === "failed" || status === "timeout" ? "error" : "warning";
  return <Chip label={status} color={color as any} size="small" />;
};

const DashboardPage = () => {
  const { data: actions } = useActions();
  const { data: jobs } = useJobs();
  const runAction = useRunAction();
  const { user } = useAuth();

  const handleRun = (id: number) => {
    runAction.mutate(id);
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        Welcome{user ? `, ${user.email}` : ""}
      </Typography>

      <Typography variant="h6" sx={{ mt: 3 }}>
        Available Actions
      </Typography>
      <Grid container spacing={2} sx={{ mt: 1 }}>
        {actions?.map((action) => (
          <Grid item xs={12} md={4} key={action.id}>
            <Card>
              <CardContent>
                <Typography variant="subtitle1">{action.name}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {action.description}
                </Typography>
              </CardContent>
              <CardActions>
                <Button size="small" onClick={() => handleRun(action.id)} disabled={runAction.isLoading}>
                  Run
                </Button>
              </CardActions>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Typography variant="h6" sx={{ mt: 4 }}>
        Recent Jobs
      </Typography>
      <Stack spacing={1} sx={{ mt: 1 }}>
        {jobs?.map((job) => (
          <Card key={job.id}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={1}>
                <StatusChip status={job.status} />
                <Typography variant="subtitle2">Job #{job.id}</Typography>
                {job.action_name && (
                  <Typography variant="body2" color="text.secondary">
                    {job.action_name}
                  </Typography>
                )}
                {job.parsed_result && (
                  <Typography variant="body2" color="text.secondary">
                    Result: {job.parsed_result}
                  </Typography>
                )}
                {job.error_message && <Alert severity="error">{job.error_message}</Alert>}
              </Stack>
              <Typography variant="caption" color="text.secondary">
                Created: {new Date(job.created_at).toLocaleString()}
              </Typography>
            </CardContent>
          </Card>
        ))}
      </Stack>
    </Box>
  );
};

export default DashboardPage;
