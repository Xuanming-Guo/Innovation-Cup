import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AuthorisedApiContext } from "./api-client";
import { CompanyConnections } from "./company-connections";
import { EmployeeWorkspace } from "./employee-workspace";
import { PlanReviewWorkspace } from "./plan-review";

const api: AuthorisedApiContext = {
  apiOrigin: "https://api.example.invalid",
  companyId: "11111111-1111-4111-8111-111111111111",
  accessToken: "test-access-token",
};

function json(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("connected workspaces", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("loads authorised sources for real manager intake", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: string | URL | Request) => {
        const url = String(input);
        if (url.endsWith("/planning-context")) {
          return Promise.resolve(
            json({
              sources: [
                {
                  source_id: "11111111-0000-4111-8111-111111111501",
                  title: "Software release commitments",
                  classification: "confidential",
                  source_kind: "fixture",
                },
              ],
              requests: [],
            }),
          );
        }
        if (url.endsWith("/reviews/pending")) return Promise.resolve(json({ reviews: [] }));
        return Promise.reject(new Error(`unexpected request ${url}`));
      }),
    );

    render(<PlanReviewWorkspace api={api} />);

    expect(await screen.findByText("Software release commitments")).toBeVisible();
    expect(screen.getByRole("button", { name: "Create checked plan" })).toBeEnabled();
    expect(screen.queryByText(/Sample data/i)).not.toBeInTheDocument();
  });

  it("renders only tasks returned by the authorised employee endpoint", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        json({
          view: "today",
          tasks: [
            {
              task_id: "11111111-0000-4111-8111-111111111901",
              task_key: "software_release_readiness",
              title: "Prepare the software release readiness pack",
              scheduling_kind: "flexible_active",
              status: "assigned",
              row_version: 1,
              start_at: "2026-09-28T09:00:00Z",
              finish_at: "2026-09-28T10:30:00Z",
              reviewer_name: "Maya Chen",
              latest_submission_id: null,
              latest_submission_version: null,
              approved_brief: {
                brief_version_id: "11111111-0000-4111-8111-111111111902",
                version: 1,
                content: { summary: "Complete the approved release-readiness work." },
              },
            },
          ],
        }),
      ),
    );

    render(<EmployeeWorkspace api={api} />);

    expect(
      await screen.findByRole("heading", {
        name: "Prepare the software release readiness pack",
      }),
    ).toBeVisible();
    expect(screen.getByText("Complete the approved release-readiness work.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Acknowledge task" })).toBeEnabled();
  });

  it("submits a company key once and renders only non-secret connection metadata", async () => {
    const fetchMock = vi.fn().mockImplementation((_input: string | URL | Request, init?: RequestInit) => {
      if (init?.method === "PUT") {
        expect(String(init.body)).toContain("test-company-gemini-key-value-0001");
        return Promise.resolve(json({
          provider: "gemini_developer_api",
          credential_kind: "api_key",
          status: "configured",
          credential_hint: "0123456789ab",
          validated_model: "gemini-test",
          vertex_project_id: null,
          vertex_client_email: null,
          vertex_location: null,
          configured_at: "2026-09-26T12:00:00Z",
          validated_at: "2026-09-26T12:00:00Z",
          rotated_at: null,
        }));
      }
      return Promise.resolve(json({
        provider: "gemini_developer_api",
        credential_kind: "api_key",
        status: "not_configured",
        credential_hint: null,
        validated_model: null,
        vertex_project_id: null,
        vertex_client_email: null,
        vertex_location: null,
        configured_at: null,
        validated_at: null,
        rotated_at: null,
      }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<CompanyConnections api={api} canManage />);
    const key = "test-company-gemini-key-value-0001";
    fireEvent.change(await screen.findByLabelText("Company API key"), {
      target: { value: key },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify and connect" }));

    expect(await screen.findByText("0123456789ab")).toBeVisible();
    expect(screen.queryByDisplayValue(key)).not.toBeInTheDocument();
    expect(screen.queryByText(key)).not.toBeInTheDocument();
  });

  it("submits Vertex JSON once and renders only its safe identity metadata", async () => {
    const privateMarker = "private-material-that-must-be-cleared";
    const serviceAccountJson = JSON.stringify({
      type: "service_account",
      project_id: "test-vertex-project",
      private_key: privateMarker,
      client_email: "agent@test-vertex-project.iam.gserviceaccount.com",
    });
    const fetchMock = vi
      .fn()
      .mockImplementation((_input: string | URL | Request, init?: RequestInit) => {
        if (init?.method === "PUT") {
          const body = JSON.parse(String(init.body)) as Record<string, string>;
          expect(body.credential_kind).toBe("vertex_service_account");
          expect(body.service_account_json).toBe(serviceAccountJson);
          expect(body.api_key).toBeUndefined();
          return Promise.resolve(
            json({
              provider: "vertex_ai",
              credential_kind: "vertex_service_account",
              status: "configured",
              credential_hint: "abcdef012345",
              validated_model: "gemini-test",
              vertex_project_id: "test-vertex-project",
              vertex_client_email: "agent@test-vertex-project.iam.gserviceaccount.com",
              vertex_location: "global",
              configured_at: "2026-09-26T12:00:00Z",
              validated_at: "2026-09-26T12:00:00Z",
              rotated_at: null,
            }),
          );
        }
        return Promise.resolve(
          json({
            provider: "gemini_developer_api",
            credential_kind: "api_key",
            status: "not_configured",
            credential_hint: null,
            validated_model: null,
            vertex_project_id: null,
            vertex_client_email: null,
            vertex_location: null,
            configured_at: null,
            validated_at: null,
            rotated_at: null,
          }),
        );
      });
    vi.stubGlobal("fetch", fetchMock);

    render(<CompanyConnections api={api} canManage />);
    await screen.findByLabelText("Company API key");
    fireEvent.click(screen.getByRole("button", { name: "Vertex service account" }));
    fireEvent.change(screen.getByLabelText("Service-account JSON"), {
      target: { value: serviceAccountJson },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify and connect" }));

    expect(await screen.findByText("test-vertex-project")).toBeVisible();
    expect(screen.getByText("agent@test-vertex-project.iam.gserviceaccount.com")).toBeVisible();
    expect(screen.queryByDisplayValue(serviceAccountJson)).not.toBeInTheDocument();
    expect(screen.queryByText(privateMarker)).not.toBeInTheDocument();
  });
});
