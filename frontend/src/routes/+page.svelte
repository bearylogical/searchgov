<script lang="ts">
	import { isAuthenticated } from '$lib/auth';

	const cards = [
		{
			href: '/progression',
			title: 'Career Progression',
			description:
				'Trace how individuals have moved across roles and organisations over time.'
		},
		{
			href: '/organisation',
			title: 'Organisation Explorer',
			description:
				'Browse the hierarchy of government organisations and see how they evolved.'
		}
	];
</script>

{#if !$isAuthenticated}
	<div class="flex flex-col items-center justify-center h-64 gap-4">
		<p class="text-gray-600">Sign in to access SGDI Analytics.</p>
		<a
			href="/login"
			class="bg-blue-600 text-white text-sm font-medium px-4 py-2 rounded hover:bg-blue-700 transition-colors"
		>
			Sign in
		</a>
	</div>
{:else}
	<h1 class="text-2xl font-bold text-gray-900 mb-6">
		Welcome to SGDI Analytics
	</h1>

	<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
		{#each cards as card}
			<a
				href={card.href}
				class="block bg-white border border-gray-200 rounded-lg p-6 shadow-sm
					hover:shadow-md hover:border-blue-300 transition-all"
			>
				<h2 class="font-semibold text-gray-900 mb-2">{card.title}</h2>
				<p class="text-sm text-gray-500">{card.description}</p>
			</a>
		{/each}
	</div>
{/if}
