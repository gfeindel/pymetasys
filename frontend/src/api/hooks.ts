import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "./client";
import { ActionDefinition, ActionJob, TokenResponse, User } from "./types";

export const useCurrentUser = () =>
  useQuery<User>({
    queryKey: ["me"],
    queryFn: async () => {
      const res = await api.get("/api/auth/me");
      return res.data;
    },
    retry: false,
  });

export const useActions = () =>
  useQuery<ActionDefinition[]>({
    queryKey: ["actions"],
    queryFn: async () => (await api.get("/api/actions")).data,
  });

export const useJobs = (statusFilter?: string) =>
  useQuery<ActionJob[]>({
    queryKey: ["jobs", statusFilter || "all"],
    queryFn: async () =>
      (
        await api.get("/api/jobs", {
          params: statusFilter ? { status_filter: statusFilter } : undefined,
        })
      ).data,
    refetchInterval: 3000,
  });

export const useLogin = () =>
  useMutation({
    mutationFn: async (payload: { email: string; password: string }): Promise<TokenResponse> => {
      const res = await api.post("/api/auth/login", payload);
      return res.data;
    },
  });

export const useRunAction = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (actionId: number) => {
      const res = await api.post(`/api/actions/${actionId}/jobs`);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
};

export const useCreateAction = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<ActionDefinition>) => (await api.post("/api/actions", payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["actions"] }),
  });
};

export const useCreateUser = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { email: string; password: string; role: string }) =>
      (await api.post("/api/users", payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
};

export const useUsers = () =>
  useQuery<User[]>({
    queryKey: ["users"],
    queryFn: async () => (await api.get("/api/users")).data,
    refetchInterval: 10000,
  });

export const useTestRegex = () =>
  useMutation({
    mutationFn: async (payload: { sample_text: string; regex: string }) =>
      (await api.post("/api/actions/test-regex", payload)).data as { matches: string[]; groups: Record<string, any> },
  });
