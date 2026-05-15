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
    "/api/v1/pipeline/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Pipeline Status
         * @description Current pipeline state: last cycle, breaker, freshness.
         */
        get: operations["pipeline_status_api_v1_pipeline_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/pipeline/cycle": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Start Cycle
         * @description Start one pipeline cycle. 409 if already running.
         */
        post: operations["start_cycle_api_v1_pipeline_cycle_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/pipeline/loop/start": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Start Loop
         * @description Start the polling loop. 409 if already active.
         */
        post: operations["start_loop_api_v1_pipeline_loop_start_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/pipeline/loop/stop": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Stop Loop
         * @description Stop the polling loop. Idempotent.
         */
        post: operations["stop_loop_api_v1_pipeline_loop_stop_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/pipeline/loop": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Loop State
         * @description Current loop state.
         */
        get: operations["loop_state_api_v1_pipeline_loop_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/pipeline/freshness": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Freshness
         * @description Per-source freshness gauges.
         */
        get: operations["freshness_api_v1_pipeline_freshness_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/pipeline/jobs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Jobs
         * @description List recent jobs.
         */
        get: operations["list_jobs_api_v1_pipeline_jobs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/pipeline/jobs/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Job
         * @description Single job detail.
         */
        get: operations["get_job_api_v1_pipeline_jobs__job_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/kalshi/credentials/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Kalshi Credentials
         * @description Check credential configuration without exposing secrets.
         */
        get: operations["kalshi_credentials_api_v1_kalshi_credentials_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/kalshi/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Kalshi Health
         * @description Ping Kalshi API and report latency + clock skew.
         */
        get: operations["kalshi_health_api_v1_kalshi_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/kalshi/series": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Kalshi Series
         * @description List available series. Returns a static list for now.
         */
        get: operations["kalshi_series_api_v1_kalshi_series_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/kalshi/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Kalshi Events
         * @description List events for a Kalshi series with alias status from warehouse.
         */
        get: operations["kalshi_events_api_v1_kalshi_events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/kalshi/events/{event_ticker}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Kalshi Event Detail
         * @description Event detail with all markets under it.
         */
        get: operations["kalshi_event_detail_api_v1_kalshi_events__event_ticker__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/kalshi/markets/{ticker}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Kalshi Market Detail
         * @description Single market detail with current prices and recent snapshots.
         */
        get: operations["kalshi_market_detail_api_v1_kalshi_markets__ticker__get"];
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
        /**
         * FreshnessEntry
         * @description Per-source freshness gauge.
         */
        FreshnessEntry: {
            /** Source */
            source: string;
            /** Last Seen At */
            last_seen_at: string | null;
            /** Age Seconds */
            age_seconds: number | null;
            /** Threshold Seconds */
            threshold_seconds: number;
            /** Status */
            status: string;
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
         * JobListResponse
         * @description GET /api/v1/pipeline/jobs response.
         */
        JobListResponse: {
            /** Jobs */
            jobs: components["schemas"]["JobResponse"][];
        };
        /**
         * JobResponse
         * @description Single job detail.
         */
        JobResponse: {
            /** Job Id */
            job_id: string;
            /** Job Type */
            job_type: string;
            /** Status */
            status: string;
            /** Started At */
            started_at: string | null;
            /** Completed At */
            completed_at: string | null;
            /** Duration S */
            duration_s: number | null;
            /** Error */
            error: string | null;
            /** Progress */
            progress: {
                [key: string]: unknown;
            }[];
        };
        /**
         * KalshiCredentialsResponse
         * @description GET /api/v1/kalshi/credentials/status response.
         */
        KalshiCredentialsResponse: {
            /** Configured */
            configured: boolean;
            /** Key Id Present */
            key_id_present: boolean;
            /** Private Key Present */
            private_key_present: boolean;
            /** Base Url */
            base_url: string;
            /** Is Demo */
            is_demo: boolean;
        };
        /**
         * KalshiEventDetailResponse
         * @description GET /api/v1/kalshi/events/{event_ticker} response.
         */
        KalshiEventDetailResponse: {
            event: components["schemas"]["KalshiEventResponse"];
            /** Markets */
            markets: components["schemas"]["KalshiMarketResponse"][];
        };
        /**
         * KalshiEventListResponse
         * @description GET /api/v1/kalshi/events response.
         */
        KalshiEventListResponse: {
            /** Events */
            events: components["schemas"]["KalshiEventResponse"][];
            /** Total */
            total: number;
        };
        /**
         * KalshiEventResponse
         * @description Single Kalshi event in a list or detail view.
         */
        KalshiEventResponse: {
            /** Event Ticker */
            event_ticker: string;
            /** Series Ticker */
            series_ticker: string;
            /** Title */
            title: string;
            /** Sub Title */
            sub_title?: string | null;
            /** Category */
            category?: string | null;
            /** Alias Status */
            alias_status?: string | null;
            /** Fixture Id */
            fixture_id?: string | null;
        };
        /**
         * KalshiHealthResponse
         * @description GET /api/v1/kalshi/health response.
         */
        KalshiHealthResponse: {
            /** Ok */
            ok: boolean;
            /** Latency Ms */
            latency_ms: number | null;
            /** Clock Skew S */
            clock_skew_s: number | null;
            /** Base Url */
            base_url: string;
            /** Error */
            error?: string | null;
        };
        /**
         * KalshiMarketDetailResponse
         * @description GET /api/v1/kalshi/markets/{ticker} response.
         */
        KalshiMarketDetailResponse: {
            market: components["schemas"]["KalshiMarketResponse"];
            /** Recent Snapshots */
            recent_snapshots: {
                [key: string]: unknown;
            }[];
        };
        /**
         * KalshiMarketResponse
         * @description Single Kalshi market with current pricing.
         */
        KalshiMarketResponse: {
            /** Ticker */
            ticker: string;
            /** Event Ticker */
            event_ticker: string;
            /** Floor Strike */
            floor_strike: string;
            /** Yes Bid */
            yes_bid: string;
            /** No Bid */
            no_bid: string;
            /** Yes Ask */
            yes_ask?: string | null;
            /** No Ask */
            no_ask?: string | null;
            /** Yes Bid Size */
            yes_bid_size?: number | null;
            /** Yes Ask Size */
            yes_ask_size?: number | null;
            /** Decimal Odds */
            decimal_odds?: string | null;
            /** Implied Probability */
            implied_probability?: string | null;
        };
        /**
         * KalshiSeriesListResponse
         * @description GET /api/v1/kalshi/series response.
         */
        KalshiSeriesListResponse: {
            /** Series */
            series: components["schemas"]["KalshiSeriesResponse"][];
        };
        /**
         * KalshiSeriesResponse
         * @description Single series entry.
         */
        KalshiSeriesResponse: {
            /** Series Ticker */
            series_ticker: string;
            /** Title */
            title: string;
            /** Category */
            category?: string | null;
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
         * LoopStateResponse
         * @description Pipeline polling loop state.
         */
        LoopStateResponse: {
            /** Active */
            active: boolean;
            /** Interval Min */
            interval_min: number | null;
            /** Started At */
            started_at: string | null;
            /** Last Cycle At */
            last_cycle_at: string | null;
            /** Cycles Completed */
            cycles_completed: number;
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
         * PipelineStatusResponse
         * @description GET /api/v1/pipeline/status response.
         */
        PipelineStatusResponse: {
            /** Last Cycle At */
            last_cycle_at: string | null;
            /** Last Cycle Duration S */
            last_cycle_duration_s: number | null;
            circuit_breaker: components["schemas"]["CircuitBreakerInfo"];
            loop: components["schemas"]["LoopStateResponse"];
            /** Freshness */
            freshness: {
                [key: string]: components["schemas"]["FreshnessEntry"];
            };
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
        /**
         * StartCycleResponse
         * @description POST /api/v1/pipeline/cycle response.
         */
        StartCycleResponse: {
            /** Job Id */
            job_id: string;
            /** Status */
            status: string;
        };
        /**
         * StartLoopRequest
         * @description POST /api/v1/pipeline/loop/start request body.
         */
        StartLoopRequest: {
            /** Interval Min */
            interval_min: number;
        };
        /**
         * StartLoopResponse
         * @description POST /api/v1/pipeline/loop/start response.
         */
        StartLoopResponse: {
            /** Loop Id */
            loop_id: string;
            /** Interval Min */
            interval_min: number;
        };
        /**
         * StopLoopResponse
         * @description POST /api/v1/pipeline/loop/stop response.
         */
        StopLoopResponse: {
            /** Ok */
            ok: boolean;
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
    pipeline_status_api_v1_pipeline_status_get: {
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
                    "application/json": components["schemas"]["PipelineStatusResponse"];
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
    start_cycle_api_v1_pipeline_cycle_post: {
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
                    "application/json": components["schemas"]["StartCycleResponse"];
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
    start_loop_api_v1_pipeline_loop_start_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: {
                session?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StartLoopRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StartLoopResponse"];
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
    stop_loop_api_v1_pipeline_loop_stop_post: {
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
                    "application/json": components["schemas"]["StopLoopResponse"];
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
    loop_state_api_v1_pipeline_loop_get: {
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
                    "application/json": components["schemas"]["LoopStateResponse"];
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
    freshness_api_v1_pipeline_freshness_get: {
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
                    "application/json": {
                        [key: string]: components["schemas"]["FreshnessEntry"];
                    };
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
    list_jobs_api_v1_pipeline_jobs_get: {
        parameters: {
            query?: {
                status?: string | null;
                limit?: number;
            };
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
                    "application/json": components["schemas"]["JobListResponse"];
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
    get_job_api_v1_pipeline_jobs__job_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
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
                    "application/json": components["schemas"]["JobResponse"];
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
    kalshi_credentials_api_v1_kalshi_credentials_status_get: {
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
                    "application/json": components["schemas"]["KalshiCredentialsResponse"];
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
    kalshi_health_api_v1_kalshi_health_get: {
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
                    "application/json": components["schemas"]["KalshiHealthResponse"];
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
    kalshi_series_api_v1_kalshi_series_get: {
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
                    "application/json": components["schemas"]["KalshiSeriesListResponse"];
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
    kalshi_events_api_v1_kalshi_events_get: {
        parameters: {
            query?: {
                series?: string;
                status?: string;
                limit?: number;
            };
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
                    "application/json": components["schemas"]["KalshiEventListResponse"];
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
    kalshi_event_detail_api_v1_kalshi_events__event_ticker__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                event_ticker: string;
            };
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
                    "application/json": components["schemas"]["KalshiEventDetailResponse"];
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
    kalshi_market_detail_api_v1_kalshi_markets__ticker__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                ticker: string;
            };
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
                    "application/json": components["schemas"]["KalshiMarketDetailResponse"];
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
