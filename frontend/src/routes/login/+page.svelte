<script lang="ts">
	import { signIn, isAuthenticated, authReady } from '$lib/auth';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';

	let email = $state('');
	let password = $state('');
	let error = $state('');
	let loading = $state(false);

	const redirectTo = page.url.searchParams.get('redirect') ?? '/';

	// Redirect away if the user is already logged in
	$effect(() => {
		if ($authReady && $isAuthenticated) goto(redirectTo);
	});

	async function handleSubmit(e: Event) {
		e.preventDefault();
		error = '';
		loading = true;
		try {
			await signIn(email, password);
			goto(redirectTo);
		} catch (err: unknown) {
			error = err instanceof Error ? err.message : 'Login failed. Please try again.';
		} finally {
			loading = false;
		}
	}
</script>

<div class="flex-1 flex items-center justify-center p-4 sm:p-8">
	<div class="w-full max-w-sm">
		<div class="text-center mb-8">
			<div class="w-12 h-12 rounded-xl bg-blue-600 flex items-center justify-center mx-auto mb-4 shadow-md">
				<svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 20 20">
					<path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z"/>
				</svg>
			</div>
			<h1 class="text-xl font-bold text-gray-900 dark:text-gray-100">SGDI Analytics</h1>
			<p class="text-sm text-gray-500 dark:text-gray-400 mt-1">Sign in to your account</p>
		</div>

		<div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl shadow-sm p-6">
			<form onsubmit={handleSubmit} class="space-y-4">
				<div class="space-y-1">
					<label for="email" class="block text-sm font-medium text-gray-700 dark:text-gray-300">
						Email address
					</label>
					<input
						id="email" type="email" bind:value={email} required autocomplete="email"
						placeholder="you@agency.gov.sg"
						class="w-full border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-2 text-sm
						       bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500
						       transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
					/>
				</div>

				<div class="space-y-1">
					<label for="password" class="block text-sm font-medium text-gray-700 dark:text-gray-300">
						Password
					</label>
					<input
						id="password" type="password" bind:value={password} required autocomplete="current-password"
						class="w-full border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-2 text-sm
						       bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500
						       transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
					/>
				</div>

				{#if error}
					<div class="flex items-start gap-2 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2.5">
						<svg class="w-4 h-4 text-red-500 mt-0.5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
							<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/>
						</svg>
						<p class="text-sm text-red-700 dark:text-red-400">{error}</p>
					</div>
				{/if}

				<button
					type="submit" disabled={loading}
					class="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold text-sm
					       px-4 py-2.5 rounded-lg transition-colors mt-2
					       disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
				>
					{#if loading}
						<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
							<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
							<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
						</svg>
						Signing in…
					{:else}
						Sign in
					{/if}
				</button>
			</form>
		</div>
	</div>
</div>
