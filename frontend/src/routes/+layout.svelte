<script lang="ts">
	import '../app.css';
	import { isAuthenticated, signOut, user } from '$lib/auth';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';

	let { children } = $props();

	// ── Dark mode ──────────────────────────────────────
	let dark = $state(false);

	$effect(() => {
		dark = document.documentElement.classList.contains('dark');
	});

	function toggleDark() {
		dark = !dark;
		document.documentElement.classList.toggle('dark', dark);
		localStorage.setItem('theme', dark ? 'dark' : 'light');
	}

	// ── Nav ────────────────────────────────────────────
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

<div class="min-h-screen bg-gray-50 dark:bg-gray-950 flex flex-col transition-colors duration-200">
	<!-- ── Header ──────────────────────────────────────── -->
	<header class="sticky top-0 z-50 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
		<div class="max-w-screen-2xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between gap-4">
			<!-- Logo + nav -->
			<div class="flex items-center gap-2 min-w-0">
				<a href="/" class="flex items-center gap-2.5 shrink-0 mr-2">
					<div class="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center shadow-sm shrink-0">
						<svg class="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 20 20">
							<path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z"/>
						</svg>
					</div>
					<span class="font-semibold text-gray-900 dark:text-gray-100 text-sm hidden sm:block tracking-tight">
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
										? 'bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-400'
										: 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800'}"
							>
								{link.label}
							</a>
						{/each}
					</nav>
				{/if}
			</div>

			<!-- Right side -->
			<div class="flex items-center gap-2 shrink-0">
				<!-- Dark mode toggle -->
				<button
					onclick={toggleDark}
					class="w-8 h-8 flex items-center justify-center rounded-lg text-gray-500 dark:text-gray-400
					       hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
					aria-label="Toggle dark mode"
				>
					{#if dark}
						<!-- Sun icon -->
						<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"/>
						</svg>
					{:else}
						<!-- Moon icon -->
						<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"/>
						</svg>
					{/if}
				</button>

				{#if $isAuthenticated}
					<span class="hidden lg:block text-xs text-gray-400 dark:text-gray-500 max-w-[180px] truncate">
						{$user?.email}
					</span>
					<div class="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold shrink-0">
						{initials}
					</div>
					<button
						onclick={handleSignOut}
						class="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100
						       transition-colors px-2 py-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800"
					>
						Sign out
					</button>
				{:else}
					<a
						href="/login"
						class="text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 px-3 py-1.5 rounded-md transition-colors"
					>
						Sign in
					</a>
				{/if}
			</div>
		</div>
	</header>

	<!-- ── Main ──────────────────────────────────────────── -->
	<main class="flex-1 flex flex-col">
		{@render children()}
	</main>

	<!-- ── Footer ────────────────────────────────────────── -->
	<footer class="py-4 border-t border-gray-100 dark:border-gray-800">
		<p class="text-xs text-gray-400 dark:text-gray-600 text-center">
			SGDI Analytics &copy; {new Date().getFullYear()}
		</p>
	</footer>
</div>
