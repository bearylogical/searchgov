<script lang="ts">
	import { signIn } from '$lib/auth';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';

	let email = $state('');
	let password = $state('');
	let error = $state('');
	let loading = $state(false);

	const redirectTo = page.url.searchParams.get('redirect') ?? '/';

	async function handleSubmit(e: Event) {
		e.preventDefault();
		error = '';
		loading = true;
		try {
			await signIn(email, password);
			goto(redirectTo);
		} catch (err: unknown) {
			error = err instanceof Error ? err.message : 'Login failed';
		} finally {
			loading = false;
		}
	}
</script>

<div class="flex items-center justify-center min-h-[60vh]">
	<div class="bg-white border border-gray-200 rounded-lg shadow-sm p-8 w-full max-w-sm">
		<h1 class="text-xl font-bold text-gray-900 mb-6">Sign in</h1>

		<form onsubmit={handleSubmit} class="flex flex-col gap-4">
			<div class="flex flex-col gap-1">
				<label for="email" class="text-sm font-medium text-gray-700">Email</label>
				<input
					id="email"
					type="email"
					bind:value={email}
					required
					autocomplete="email"
					class="border border-gray-300 rounded px-3 py-2 text-sm
						focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
				/>
			</div>

			<div class="flex flex-col gap-1">
				<label for="password" class="text-sm font-medium text-gray-700">Password</label>
				<input
					id="password"
					type="password"
					bind:value={password}
					required
					autocomplete="current-password"
					class="border border-gray-300 rounded px-3 py-2 text-sm
						focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
				/>
			</div>

			{#if error}
				<p class="text-sm text-red-600">{error}</p>
			{/if}

			<button
				type="submit"
				disabled={loading}
				class="bg-blue-600 text-white text-sm font-medium px-4 py-2 rounded
					hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors mt-2"
			>
				{loading ? 'Signing in…' : 'Sign in'}
			</button>
		</form>
	</div>
</div>
