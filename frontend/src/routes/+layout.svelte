<script lang="ts">
	import '../app.css';
	import { isAuthenticated, signOut, user } from '$lib/auth';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';

	let { children } = $props();

	const navLinks = [
		{ href: '/', label: 'Home' },
		{ href: '/progression', label: 'Progression' },
		{ href: '/organisation', label: 'Organisations' }
	];

	const initials = $derived(
		$user?.email ? $user.email.slice(0, 2).toUpperCase() : '?'
	);

	async function handleSignOut() {
		await signOut();
		goto('/login');
	}
</script>

<div class="min-h-screen bg-gray-50 flex flex-col">
	<!-- ── Header ─────────────────────────────────────────── -->
	<header class="sticky top-0 z-50 bg-white border-b border-gray-200">
		<div
			class="max-w-screen-2xl mx-auto px-4 sm:px-6 lg:px-8 h-14
			       flex items-center justify-between gap-4"
		>
			<!-- Logo + nav -->
			<div class="flex items-center gap-2 min-w-0">
				<a href="/" class="flex items-center gap-2.5 shrink-0 mr-2">
					<div
						class="w-8 h-8 rounded-lg bg-blue-600 flex items-center
						       justify-center shadow-sm shrink-0"
					>
						<svg class="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 20 20">
							<path
								d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4
								10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0
								011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0
								001.414-1.414l-7-7z"
							/>
						</svg>
					</div>
					<span class="font-semibold text-gray-900 text-sm hidden sm:block tracking-tight">
						SGDI Analytics
					</span>
				</a>

				{#if $isAuthenticated}
					<nav class="hidden md:flex items-center gap-0.5">
						{#each navLinks as link}
							<a
								href={link.href}
								class="px-3 py-1.5 rounded-md text-sm font-medium transition-colors
									{page.url.pathname === link.href
										? 'bg-blue-50 text-blue-700'
										: 'text-gray-500 hover:text-gray-900 hover:bg-gray-100'}"
							>
								{link.label}
							</a>
						{/each}
					</nav>
				{/if}
			</div>

			<!-- User area -->
			<div class="flex items-center gap-2 shrink-0">
				{#if $isAuthenticated}
					<span class="hidden lg:block text-xs text-gray-400 max-w-[180px] truncate">
						{$user?.email}
					</span>
					<div
						class="w-7 h-7 rounded-full bg-blue-600 flex items-center
						       justify-center text-white text-xs font-bold shrink-0"
					>
						{initials}
					</div>
					<button
						onclick={handleSignOut}
						class="text-sm text-gray-500 hover:text-gray-900 transition-colors
						       px-2 py-1 rounded-md hover:bg-gray-100"
					>
						Sign out
					</button>
				{:else}
					<a
						href="/login"
						class="text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700
						       px-3 py-1.5 rounded-md transition-colors"
					>
						Sign in
					</a>
				{/if}
			</div>
		</div>
	</header>

	<!-- ── Main ───────────────────────────────────────────── -->
	<main class="flex-1 flex flex-col">
		{@render children()}
	</main>

	<!-- ── Footer ─────────────────────────────────────────── -->
	<footer class="py-4 border-t border-gray-100">
		<p class="text-xs text-gray-400 text-center">
			SGDI Analytics &copy; {new Date().getFullYear()}
		</p>
	</footer>
</div>
