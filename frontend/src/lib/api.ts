import { getAccessToken } from '$lib/auth';

const BASE = '/api/v1';

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------
async function apiFetch<T>(
	path: string,
	options: RequestInit = {}
): Promise<T> {
	const token = await getAccessToken();
	const headers: Record<string, string> = {
		'Content-Type': 'application/json',
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
	org_name: string;
	rank: string | null;
	start_date: string | null;
	end_date: string | null;
	tenure_days: number | null;
}

export interface PersonResult {
	person_id: number;
	name: string;
	clean_name: string;
	email: string | null;
	tel: string | null;
}

export interface OrgResult {
	org_id: number;
	name: string;
	department: string | null;
	url: string | null;
}

export interface PathNode {
	node_id: string;
	node_type: string;
	name: string;
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

	careerByName: (name: string) =>
		apiFetch<EmploymentEntry[]>(
			`/people/career?name=${encodeURIComponent(name)}`
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
		)
};

// ---------------------------------------------------------------------------
// Graph
// ---------------------------------------------------------------------------
export const graph = {
	path: (fromId: number, toId: number, temporal = false) =>
		apiFetch<PathNode[]>(
			`/graph/path?from_id=${fromId}&to_id=${toId}&temporal=${temporal}`
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
