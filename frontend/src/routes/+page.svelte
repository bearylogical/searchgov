<script lang="ts">
	import { onMount } from 'svelte';
	import { system } from '$lib/api';
	import { isAuthenticated, user } from '$lib/auth';

	let stats = $state<Record<string, Record<string, number>> | null>(null);
	let statsLoading = $state(true);

	onMount(async () => {
		if (!$isAuthenticated) return;
		try {
			stats = (await system.stats()) as Record<string, Record<string, number>>;
		} catch {
			/* stats are decorative — fail silently */
		} finally {
			statsLoading = false;
		}
	});

	function fmt(n?: number) {
		if (n == null) return '—';
		return n.toLocaleString();
	}

	const statCards = $derived([
		{
			label: 'Unique people',
			value: stats?.people_count?.unique_names,
			icon: `<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/>`,
			color: 'blue'
		},
		{
			label: 'Organisations',
			value: stats?.orgs_count?.total_organizations,
			icon: `<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21"/>`,
			color: 'violet'
		},
		{
			label: 'Employment records',
			value: stats?.employment_count?.total_employments,
			icon: `<path stroke-linecap="round" stroke-linejoin="round" d="M20.25 14.15v4.25c0 1.094-.787 2.036-1.872 2.18-2.087.277-4.216.42-6.378.42s-4.291-.143-6.378-.42c-1.085-.144-1.872-1.086-1.872-2.18v-4.25m16.5 0a2.18 2.18 0 00.75-1.661V8.706c0-1.081-.768-2.015-1.837-2.175a48.114 48.114 0 00-3.413-.387m4.5 8.006c-.194.165-.42.295-.673.38A23.978 23.978 0 0112 15.75c-2.648 0-5.195-.429-7.577-1.22a2.016 2.016 0 01-.673-.38m0 0A2.18 2.18 0 013 12.489V8.706c0-1.081.768-2.015 1.837-2.175a48.111 48.111 0 013.413-.387m7.5 0V5.25A2.25 2.25 0 0013.5 3h-3a2.25 2.25 0 00-2.25 2.25v.894m7.5 0a48.667 48.667 0 00-7.5 0"/>`,
			color: 'emerald'
		}
	]);

	const featureCards = [
		{
			href: '/progression',
			title: 'Career Progression',
			description: 'Trace how individuals have moved across roles and organisations over time.',
			icon: `<path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"/>`
		},
		{
			href: '/organisation',
			title: 'Organisation Explorer',
			description: 'Browse the hierarchy of government organisations and see how they evolved.',
			icon: `<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 3.75h.008v.008h-.008v-.008zm0 3h.008v.008h-.008v-.008zm0 3h.008v.008h-.008v-.008z"/>`
		},
		{
			href: '/connectivity',
			title: 'Connectivity Explorer',
			description: 'Find how any two people are connected through shared organisations and when those connections existed.',
			icon: `<path stroke-linecap="round" stroke-linejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5"/>`
		}
	];
</script>

{#if !$isAuthenticated}
	<div class="flex-1 flex items-center justify-center p-8">
		<div class="text-center max-w-md">
			<div class="w-16 h-16 rounded-2xl bg-blue-600 flex items-center justify-center mx-auto mb-6 shadow-lg">
				<svg class="w-8 h-8 text-white" fill="currentColor" viewBox="0 0 20 20">
					<path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z"/>
				</svg>
			</div>
			<h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">SGDI Analytics</h1>
			<p class="text-gray-500 dark:text-gray-400 mb-8 text-sm leading-relaxed">
				Explore Singapore's government employment data — career histories,
				organisational hierarchies, and workforce patterns.
			</p>
			<a href="/login" class="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold text-sm px-5 py-2.5 rounded-lg transition-colors">
				Sign in to continue
				<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3"/>
				</svg>
			</a>
		</div>
	</div>
{:else}
	<div class="max-w-5xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-10 space-y-10">
		<div>
			<h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100">Welcome back</h1>
			<p class="text-gray-500 dark:text-gray-400 text-sm mt-1">{$user?.email}</p>
		</div>

		<!-- Stats row -->
		<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
			{#each statCards as card}
				<div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5 shadow-sm">
					<div class="flex items-start justify-between">
						<div>
							{#if statsLoading}
								<div class="h-8 w-24 bg-gray-100 dark:bg-gray-800 rounded animate-pulse mb-1"></div>
								<div class="h-4 w-32 bg-gray-100 dark:bg-gray-800 rounded animate-pulse"></div>
							{:else}
								<p class="text-2xl font-bold text-gray-900 dark:text-gray-100 tabular-nums">{fmt(card.value)}</p>
								<p class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{card.label}</p>
							{/if}
						</div>
						<div class="w-9 h-9 rounded-lg flex items-center justify-center shrink-0
							{card.color === 'blue' ? 'bg-blue-50 dark:bg-blue-950' : card.color === 'violet' ? 'bg-violet-50 dark:bg-violet-950' : 'bg-emerald-50 dark:bg-emerald-950'}">
							<svg class="w-5 h-5 {card.color === 'blue' ? 'text-blue-600 dark:text-blue-400' : card.color === 'violet' ? 'text-violet-600 dark:text-violet-400' : 'text-emerald-600 dark:text-emerald-400'}"
								fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
								{@html card.icon}
							</svg>
						</div>
					</div>
				</div>
			{/each}
		</div>

		<!-- Feature cards -->
		<div>
			<h2 class="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-4">Explore</h2>
			<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
				{#each featureCards as card}
					<a href={card.href}
						class="group bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-6 shadow-sm
						       hover:shadow-md hover:border-blue-200 dark:hover:border-blue-800 transition-all">
						<div class="w-10 h-10 rounded-lg bg-blue-50 dark:bg-blue-950 flex items-center justify-center mb-4">
							<svg class="w-5 h-5 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
								{@html card.icon}
							</svg>
						</div>
						<h3 class="font-semibold text-gray-900 dark:text-gray-100 mb-1">{card.title}</h3>
						<p class="text-sm text-gray-500 dark:text-gray-400 leading-relaxed mb-4">{card.description}</p>
						<span class="inline-flex items-center gap-1 text-sm font-medium text-blue-600 dark:text-blue-400 group-hover:gap-2 transition-all">
							Explore
							<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3"/>
							</svg>
						</span>
					</a>
				{/each}
			</div>
		</div>
	</div>
{/if}
