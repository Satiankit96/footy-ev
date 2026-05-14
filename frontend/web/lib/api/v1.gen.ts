// AUTO-GENERATED — do not edit manually.
// Regenerate with: pnpm types:gen
// Source: http://localhost:8000/api/v1/openapi.json

export interface paths {
    "/api/v1/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Health
         * @description Liveness probe. No auth required.
         */
        get: operations["health_api_v1_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Login
         * @description Validate operator token. Sets HttpOnly session cookie on success.
         */
        post: operations["login_api_v1_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Logout
         * @description Clear the session cookie.  Always succeeds.
         */
        post: operations["logout_api_v1_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Me
         * @description Return current operator info from the session JWT.
         */
        get: operations["me_api_v1_auth_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/shell": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Shell
         * @description Return venue, circuit breaker, and pipeline state for the app shell.
         */
        get: operations["shell_api_v1_shell_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * CircuitBreakerInfo
         * @description Circuit breaker state.
         */
        CircuitBreakerInfo: {
            /** State */
            state: string;
            /** Last Tripped At */
            last_tripped_at: string | null;
            /** Reason */
            reason: string | null;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * HealthResponse
         * @description GET /api/v1/health response.
         */
        HealthResponse: {
            /** Status */
            status: string;
            /** Version */
            version: string;
            /** Uptime S */
            uptime_s: number;
            /** Active Venue */
            active_venue?: string | null;
        };
        /**
         * LoginRequest
         * @description POST /api/v1/auth/login request body.
         */
        LoginRequest: {
            /** Token */
            token: string;
        };
        /**
         * LoginResponse
         * @description POST /api/v1/auth/login response.
         */
        LoginResponse: {
            /** Ok */
            ok: boolean;
        };
        /**
         * LogoutResponse
         * @description POST /api/v1/auth/logout response.
         */
        LogoutResponse: {
            /** Ok */
            ok: boolean;
        };
        /**
         * MeResponse
         * @description GET /api/v1/auth/me response.
         */
        MeResponse: {
            /** Operator */
            operator: string;
            /** Session Started At */
            session_started_at: string | null;
        };
        /**
         * PipelineInfo
         * @description Pipeline loop state.
         */
        PipelineInfo: {
            /** Loop Active */
            loop_active: boolean;
            /** Last Cycle At */
            last_cycle_at: string | null;
        };
        /**
         * ShellResponse
         * @description GET /api/v1/shell response.
         */
        ShellResponse: {
            /** Operator */
            operator: string;
            venue: components["schemas"]["VenueInfo"];
            circuit_breaker: components["schemas"]["CircuitBreakerInfo"];
            pipeline: components["schemas"]["PipelineInfo"];
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
        /**
         * VenueInfo
         * @description Venue configuration state.
         */
        VenueInfo: {
            /** Name */
            name: string;
            /** Base Url */
            base_url: string;
            /** Is Demo */
            is_demo: boolean;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    health_api_v1_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
    login_api_v1_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LoginResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    logout_api_v1_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LogoutResponse"];
                };
            };
        };
    };
    me_api_v1_auth_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: {
                session?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MeResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    shell_api_v1_shell_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: {
                session?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ShellResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
