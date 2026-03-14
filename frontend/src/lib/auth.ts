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

// Initialise from existing session (e.g. after page refresh).
supabase.auth.getSession().then(({ data }) => {
	_session.set(data.session);
});

// Keep store in sync with Supabase auth events.
supabase.auth.onAuthStateChange((_event, session) => {
	_session.set(session);
});

export const session = { subscribe: _session.subscribe };
export const user = derived(_session, (s): User | null => s?.user ?? null);
export const isAuthenticated = derived(_session, (s) => s !== null);

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
