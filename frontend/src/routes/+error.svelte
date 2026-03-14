<script lang="ts">
	import { page } from '$app/state';
</script>

<div class="flex-1 flex items-center justify-center p-8">
	<div class="text-center">
		<p class="text-8xl font-bold text-gray-100 dark:text-gray-800 select-none leading-none mb-4">{page.status}</p>
		<h1 class="text-xl font-semibold text-gray-800 dark:text-gray-200 mb-2">
			{page.status === 404 ? 'Page not found' : 'Something went wrong'}
		</h1>
		<p class="text-sm text-gray-500 dark:text-gray-400 mb-8 max-w-sm">
			{page.error?.message ?? 'An unexpected error occurred. Please try again.'}
		</p>
		<a href="/"
			class="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700
			       text-white font-semibold text-sm px-4 py-2 rounded-lg transition-colors">
			<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18"/>
			</svg>
			Back to home
		</a>
	</div>
</div>
