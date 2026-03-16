<script lang="ts">
	import '../app.css';
	import { isAuthenticated, signOut, user } from '$lib/auth';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';

	let { children } = $props();

	// ── Dark mode ──────────────────────────────────────
	let dark = $state(true); // Palantir: dark-first default

	$effect(() => {
		const stored = localStorage.getItem('theme');
		if (stored) {
			dark = stored === 'dark';
		}
		// Always start dark unless user explicitly chose light
		document.documentElement.classList.toggle('dark', dark);
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
		{ href: '/organisation', label: 'Organisations' },
		{ href: '/connectivity', label: 'Connectivity' }
	];

	const initials = $derived(
		$user?.email ? $user.email.slice(0, 2).toUpperCase() : '?'
	);

	async function handleSignOut() {
		await signOut();
		goto('/login');
	}

	// ── Mobile nav ─────────────────────────────────────
	let mobileNavOpen = $state(false);

	function closeMobileNav() {
		mobileNavOpen = false;
	}
</script>

<div class="min-h-screen bg-[--pt-bg-0] dark:bg-[--pt-bg-0] flex flex-col transition-colors duration-200">
	<!-- ── Mobile nav overlay ───────────────────────── -->
	{#if mobileNavOpen}
		<!-- Backdrop -->
		<div
			class="fixed inset-0 z-40 bg-black/60 md:hidden"
			role="button"
			tabindex="-1"
			onclick={closeMobileNav}
			onkeydown={(e) => e.key === 'Escape' && closeMobileNav()}
		></div>

		<!-- Slide-in drawer -->
		<div class="fixed top-0 left-0 bottom-0 z-50 w-64 flex flex-col md:hidden"
		     style="background: var(--pt-bg-1); border-right: 1px solid var(--pt-border);">
			<!-- Drawer header -->
			<div class="flex items-center justify-between px-4 h-14"
			     style="border-bottom: 1px solid var(--pt-border);">
				<div class="flex items-center gap-2">
					<img src="/lion_search.png" alt="" class="w-6 h-6 object-contain" />
					<span class="text-sm font-semibold" style="color: var(--pt-text-primary); letter-spacing: 0.04em;">SGDI Analytics</span>
				</div>
				<button onclick={closeMobileNav}
				        class="w-8 h-8 flex items-center justify-center rounded transition-colors"
				        style="color: var(--pt-text-muted);"
				        aria-label="Close menu">
					<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
					</svg>
				</button>
			</div>

			<!-- Nav links -->
			{#if $isAuthenticated}
				<nav class="flex-1 overflow-y-auto py-2">
					{#each navLinks as link}
						<a
							href={link.href}
							onclick={closeMobileNav}
							class="flex items-center px-4 py-3 text-sm font-semibold tracking-wider uppercase transition-colors"
							style={page.url.pathname === link.href
								? 'color: #68b9e5; background: var(--pt-blue-tint); border-left: 2px solid var(--pt-blue);'
								: 'color: var(--pt-text-secondary);'}
						>
							{link.label}
						</a>
					{/each}
				</nav>
			{/if}

			<!-- User info at bottom -->
			{#if $isAuthenticated}
				<div class="p-4" style="border-top: 1px solid var(--pt-border);">
					<p class="text-sm truncate mb-3" style="color: var(--pt-text-muted);">{$user?.email}</p>
					<button
						onclick={() => { handleSignOut(); closeMobileNav(); }}
						class="w-full pt-button pt-button-outlined text-sm"
					>
						Sign out
					</button>
				</div>
			{/if}
		</div>
	{/if}

	<!-- ── Header ──────────────────────────────────────── -->
	<header class="sticky top-0 z-30 flex-none" style="background: var(--pt-bg-1); border-bottom: 1px solid var(--pt-border);">
		<div class="max-w-screen-2xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between gap-4">
			<!-- Left: hamburger (mobile) + logo + nav -->
			<div class="flex items-center gap-2 min-w-0">
				<!-- Hamburger (mobile only) -->
				{#if $isAuthenticated}
					<button
						onclick={() => (mobileNavOpen = !mobileNavOpen)}
						class="md:hidden w-8 h-8 flex items-center justify-center rounded transition-colors mr-1"
						style="color: var(--pt-text-muted);"
						aria-label="Toggle navigation"
					>
						<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"/>
						</svg>
					</button>
				{/if}

				<!-- Logo -->
				<a href="/" class="flex items-center gap-2 shrink-0 mr-2">
					<img src="/lion_search.png" alt="SGDI Analytics" class="w-8 h-8 object-contain" />
					<span class="font-semibold text-sm tracking-widest uppercase hidden sm:block"
					      style="color: var(--pt-text-primary); letter-spacing: 0.1em;">
						SGDI Analytics
					</span>
				</a>

				<!-- Desktop nav -->
				{#if $isAuthenticated}
					<nav class="hidden md:flex items-center gap-0.5">
						{#each navLinks as link}
							<a
								href={link.href}
								class="px-3 py-1.5 text-sm font-semibold tracking-wider uppercase transition-colors"
								style={page.url.pathname === link.href
									? 'color: #68b9e5; background: var(--pt-blue-tint); border-radius: 2px;'
									: 'color: var(--pt-text-muted);'}
								onmouseover={(e) => {
									if (page.url.pathname !== link.href) {
										(e.currentTarget as HTMLElement).style.color = 'var(--pt-text-secondary)';
										(e.currentTarget as HTMLElement).style.background = 'var(--pt-bg-3)';
										(e.currentTarget as HTMLElement).style.borderRadius = '2px';
									}
								}}
								onmouseout={(e) => {
									if (page.url.pathname !== link.href) {
										(e.currentTarget as HTMLElement).style.color = 'var(--pt-text-muted)';
										(e.currentTarget as HTMLElement).style.background = '';
									}
								}}
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
					class="w-8 h-8 flex items-center justify-center rounded transition-colors"
					style="color: var(--pt-text-muted);"
					aria-label="Toggle dark mode"
					onmouseover={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--pt-bg-3)'; }}
					onmouseout={(e) => { (e.currentTarget as HTMLElement).style.background = ''; }}
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
					<span class="hidden lg:block text-sm max-w-[180px] truncate" style="color: var(--pt-text-muted);">
						{$user?.email}
					</span>
					<div class="w-7 h-7 flex items-center justify-center text-white text-sm font-bold shrink-0"
					     style="background: var(--pt-blue); border-radius: 2px; font-family: var(--font-mono);">
						{initials}
					</div>
					<button
						onclick={handleSignOut}
						class="hidden sm:block text-sm font-medium px-2.5 py-1.5 rounded transition-colors"
						style="color: var(--pt-text-muted); border: 1px solid var(--pt-border); border-radius: 2px;"
						onmouseover={(e) => {
							(e.currentTarget as HTMLElement).style.color = 'var(--pt-text-primary)';
							(e.currentTarget as HTMLElement).style.background = 'var(--pt-bg-3)';
						}}
						onmouseout={(e) => {
							(e.currentTarget as HTMLElement).style.color = 'var(--pt-text-muted)';
							(e.currentTarget as HTMLElement).style.background = '';
						}}
					>
						Sign out
					</button>
				{:else}
					<a
						href="/login"
						class="pt-button pt-button-primary text-sm"
					>
						Sign in
					</a>
				{/if}
			</div>
		</div>
	</header>

	<!-- ── Main ──────────────────────────────────────────── -->
	<main class="flex-1 flex flex-col min-h-0">
		{@render children()}
	</main>

	<!-- ── Footer ────────────────────────────────────────── -->
	<footer class="py-3 flex-none" style="border-top: 1px solid var(--pt-border-muted);">
		<p class="text-xs text-center pt-label">
			SGDI Analytics &copy; {new Date().getFullYear()}
		</p>
	</footer>
</div>
