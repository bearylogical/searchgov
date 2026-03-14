<script lang="ts">
	import { isAuthenticated, signOut, user } from '$lib/auth';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';

	let { children } = $props();

	const navLinks = [
		{ href: '/', label: 'Home' },
		{ href: '/progression', label: 'Career Progression' },
		{ href: '/organisation', label: 'Organisation' }
	];

	async function handleSignOut() {
		await signOut();
		goto('/login');
	}
</script>

<svelte:head>
	<title>SGDI Analytics</title>
</svelte:head>

<div class="min-h-screen bg-gray-50 flex flex-col">
	<!-- Header -->
	<header class="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
		<div class="flex items-center gap-6">
			<a href="/" class="font-bold text-lg text-gray-900">SGDI Analytics</a>
			{#if $isAuthenticated}
				<nav class="flex gap-4">
					{#each navLinks as link}
						<a
							href={link.href}
							class="text-sm font-medium transition-colors
								{page.url.pathname === link.href
									? 'text-blue-600'
									: 'text-gray-600 hover:text-gray-900'}"
						>
							{link.label}
						</a>
					{/each}
				</nav>
			{/if}
		</div>

		<div class="flex items-center gap-3">
			{#if $isAuthenticated}
				<span class="text-sm text-gray-500">{$user?.email}</span>
				<button
					onclick={handleSignOut}
					class="text-sm text-gray-600 hover:text-gray-900 border border-gray-300
						rounded px-3 py-1 hover:bg-gray-50 transition-colors"
				>
					Sign out
				</button>
			{:else}
				<a
					href="/login"
					class="text-sm font-medium text-blue-600 hover:text-blue-800"
				>
					Sign in
				</a>
			{/if}
		</div>
	</header>

	<!-- Main content -->
	<main class="flex-1 max-w-6xl w-full mx-auto px-6 py-8">
		{@render children()}
	</main>

	<!-- Footer -->
	<footer class="border-t border-gray-200 px-6 py-4 text-center text-xs text-gray-400">
		SGDI Analytics &copy; {new Date().getFullYear()}
	</footer>
</div>
