import { createClient } from '@supabase/supabase-js';
import { writable, derived } from 'svelte/store';
import type { Session, User } from '@supabase/supabase-js';

// Vite exposes env vars prefixed with VITE_ to the browser bundle.
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string;
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

export const supabase = createClient(supabaseUrl, supabaseKey);

// ---------------------------------------------------------------------------
// Reactive session store
// ---------------------------------------------------------------------------
const _session = writable<Session | null>(null);
// True until the initial getSession() check completes.
// Guards against false redirects to /login while localStorage is being read.
const _ready = writable(false);

// Initialise from existing session (e.g. after page refresh).
supabase.auth.getSession().then(({ data }) => {
	_session.set(data.session);
	_ready.set(true);
});

// Keep store in sync with Supabase auth events (token refresh, sign-out, etc.)
supabase.auth.onAuthStateChange((_event, session) => {
	_session.set(session);
	_ready.set(true);
});

export const session = { subscribe: _session.subscribe };
export const user = derived(_session, (s): User | null => s?.user ?? null);
export const isAuthenticated = derived(_session, (s) => s !== null);
/** False while the initial session check is in flight — use this to gate auth redirects. */
export const authReady = { subscribe: _ready.subscribe };

// ---------------------------------------------------------------------------
// Auth helpers
// ---------------------------------------------------------------------------
export async function signIn(email: string, password: string) {
	const { error } = await supabase.auth.signInWithPassword({
		email,
		password
	});
	if (error) throw error;
}

export async function signOut() {
	const { error } = await supabase.auth.signOut();
	if (error) throw error;
}

/** Return the current access token for Authorization headers. */
export async function getAccessToken(): Promise<string | null> {
	const { data } = await supabase.auth.getSession();
	return data.session?.access_token ?? null;
}
