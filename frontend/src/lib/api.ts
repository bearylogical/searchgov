import { getAccessToken } from '$lib/auth';

const BASE = '/api/v1';

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------
async function apiFetch<T>(
	path: string,
	options: RequestInit = {}
): Promise<T> {
	let token: string | null = null;
	try {
		token = await getAccessToken();
	} catch {
		// Supabase client may throw if it can't parse a stored/refreshed session
		// (e.g. self-signed cert rejection in Firefox). Proceed without a token so
		// the server returns a clean 401 rather than crashing the call.
	}
	const isWriteMethod = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(
		(options.method ?? 'GET').toUpperCase()
	);
	const headers: Record<string, string> = {
		...(isWriteMethod ? { 'Content-Type': 'application/json' } : {}),
		...(options.headers as Record<string, string>)
	};
	if (token) headers['Authorization'] = `Bearer ${token}`;

	const res = await fetch(`${BASE}${path}`, { ...options, headers });
	if (!res.ok) {
		const body = await res.text();
		throw new Error(`API ${res.status}: ${body}`);
	}
	return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Type stubs — extend as schemas grow
// ---------------------------------------------------------------------------
export interface EmploymentEntry {
	id?: number;
	person_id?: number;
	org_id?: number;
	/** Name of the organisation — present on employment + career endpoints */
	org_name?: string;
	/** Alternate field name used by career-progression endpoint */
	entity_name?: string;
	person_name?: string;
	rank: string | null;
	start_date: string | null;
	end_date: string | null;
	tenure_days: number | null;
	raw_name?: string;
	metadata?: Record<string, unknown>;
}

export interface PersonResult {
	id: number;
	name: string;
	clean_name: string;
	email: string | null;
	tel: string | null;
	employment_profile?: EmploymentEntry[];
	sim_score?: number;
}

export interface OrgResult {
	id: number;
	name: string;
	department: string | null;
	url: string | null;
	parent_org_id?: number | null;
	sim_score?: number;
	metadata?: Record<string, unknown>;
}

export interface NameVariant {
	name: string;
	/** fuzzywuzzy token_set_ratio score 0–100 */
	score: number;
}

export interface PathNode {
	node_id: string;
	node_type: 'person' | 'organization';
	name: string;
	person_id?: number;
	org_id?: number;
	employment_profile?: EmploymentEntry[];
}

export interface ColleagueEdge {
	id: number;
	name: string;
	/** org_ids where they overlapped */
	shared_organizations: number[];
	/** "direct" or the intermediate person_id */
	connection_through: 'direct' | number;
}

export interface ColleagueNetwork {
	source_persons: { id: number; name: string }[];
	colleagues_by_degree: Record<string, ColleagueEdge[]>;
	summary: {
		total_colleagues: number;
		max_degree_searched: number;
		source_person_count: number;
	};
}

// ---------------------------------------------------------------------------
// People
// ---------------------------------------------------------------------------
export const people = {
	search: (q: string, fuzzy = true) =>
		apiFetch<PersonResult[]>(
			`/people/search?q=${encodeURIComponent(q)}&fuzzy=${fuzzy}`
		),

	employment: (personId: number) =>
		apiFetch<EmploymentEntry[]>(`/people/${personId}/employment`),

	career: (personId: number) =>
		apiFetch<EmploymentEntry[]>(`/people/${personId}/career`),

	careerByName: (name: string, fuzzy = true, threshold = 0.5) =>
		apiFetch<EmploymentEntry[]>(
			`/people/career?name=${encodeURIComponent(name)}&fuzzy=${fuzzy}&threshold=${threshold}`
		),

	similarNames: (name: string, limit = 10, threshold = 0.5) =>
		apiFetch<NameVariant[]>(
			`/people/similar-names?q=${encodeURIComponent(name)}&limit=${limit}&threshold=${threshold}`
		),

	colleagues: (personId: number, date?: string) => {
		const q = date ? `?date=${date}` : '';
		return apiFetch<PersonResult[]>(`/people/${personId}/colleagues${q}`);
	},

	connections: (personId: number, limit = 50) =>
		apiFetch<PersonResult[]>(
			`/people/${personId}/connections?limit=${limit}`
		)
};

// ---------------------------------------------------------------------------
// Organisations
// ---------------------------------------------------------------------------
export const organisations = {
	search: (q: string) =>
		apiFetch<OrgResult[]>(
			`/organisations/search?q=${encodeURIComponent(q)}`
		),

	roots: () => apiFetch<OrgResult[]>('/organisations/roots'),

	tree: (orgId: number, date?: string) => {
		const q = date ? `?date=${date}` : '';
		return apiFetch<OrgResult[]>(`/organisations/${orgId}/tree${q}`);
	},

	timeline: (orgId: number) =>
		apiFetch<string[]>(`/organisations/${orgId}/timeline`),

	diff: (orgId: number, from: string, to: string) =>
		apiFetch<Record<string, OrgResult[]>>(
			`/organisations/${orgId}/diff?from=${from}&to=${to}`
		),

	get: (orgId: number) =>
		apiFetch<OrgResult>(`/organisations/${orgId}`),

	root: (orgId: number) =>
		apiFetch<OrgResult>(`/organisations/${orgId}/root`),

	headcount: (orgId: number, date?: string) => {
		const q = date ? `?date=${date}` : '';
		return apiFetch<{ headcount: number; date: string }>(
			`/organisations/${orgId}/headcount${q}`
		);
	}
};

// ---------------------------------------------------------------------------
// Graph
// ---------------------------------------------------------------------------
export const graph = {
	path: (fromIds: number[], toIds: number[], temporal = true) => {
		const from = fromIds.map(id => `from_id=${id}`).join('&');
		const to   = toIds.map(id => `to_id=${id}`).join('&');
		return apiFetch<{ nodes: PathNode[]; length: number }>(
			`/graph/path?${from}&${to}&temporal=${temporal}`
		);
	},

	personNetwork: (personId: number, degree = 1) =>
		apiFetch<ColleagueNetwork>(
			`/graph/person/${personId}/network?degree=${degree}`
		),

	network: (date?: string) => {
		const q = date ? `?date=${date}` : '';
		return apiFetch<Record<string, unknown>>(`/graph/network${q}`);
	},

	centrality: (date?: string) => {
		const q = date ? `?date=${date}` : '';
		return apiFetch<Record<string, number>>(`/graph/centrality${q}`);
	}
};

// ---------------------------------------------------------------------------
// System
// ---------------------------------------------------------------------------
export const system = {
	health: () => apiFetch<{ status: string }>('/system/health'),
	stats: () => apiFetch<Record<string, unknown>>('/system/stats'),
	search: (q: string) =>
		apiFetch<Record<string, unknown[]>>(
			`/system/search?q=${encodeURIComponent(q)}`
		)
};
