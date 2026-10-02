// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL
#include "haptics_pcm_audit.h"

#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <random>
#include <vector>

using namespace ChiakiHapticsAudit;

static void Put(std::vector<uint8_t> &v, int32_t n)
{
	const uint32_t u = static_cast<uint32_t>(n) & 0xffffu;
	v.push_back(static_cast<uint8_t>(u & 0xffu));
	v.push_back(static_cast<uint8_t>(u >> 8));
}

static std::array<uint16_t, 2> NativeLoop(const std::vector<uint8_t> &v)
{
	uint64_t sums[2] = {0, 0};
	for(size_t i = 0; i < v.size(); i += 4)
	{
		for(size_t c = 0; c < 2; ++c)
		{
			int16_t value;
			std::memcpy(&value, &v[i + c * 2], sizeof(value));
			sums[c] += static_cast<uint64_t>(
				std::fabs(static_cast<double>(value))) * 2;
		}
	}
	const uint64_t frames = v.size() / 4;
	return {
		static_cast<uint16_t>(std::min<uint64_t>(65535, sums[0] / frames)),
		static_cast<uint16_t>(std::min<uint64_t>(65535, sums[1] / frames)),
	};
}

int main()
{
	const uint16_t endian = 1;
	if(*reinterpret_cast<const uint8_t *>(&endian) != 1)
	{
		std::cerr << "Native-loop comparison requires a little-endian host\n";
		return 2;
	}

	Stats stats;
	assert(!InspectS16LEStereo(nullptr, 120, stats));
	const uint8_t invalid[5]{};
	for(size_t n : {0u, 1u, 2u, 3u, 5u})
		assert(!InspectS16LEStereo(invalid, n, stats));

	for(int32_t x = -32768; x <= 32767; ++x)
	{
		std::vector<uint8_t> left, right;
		Put(left, x); Put(left, 0);
		Put(right, 0); Put(right, x);

		Stats l, r;
		assert(InspectS16LEStereo(left.data(), left.size(), l));
		assert(InspectS16LEStereo(right.data(), right.size(), r));
		assert(l.channel[1].peak == 0 && r.channel[0].peak == 0);
		assert(l.Envelope(0) == r.Envelope(1));
		assert(l.Envelope(0) == NativeLoop(left)[0]);
		assert(r.Envelope(1) == NativeLoop(right)[1]);
	}

	std::mt19937 rng(0x414c4c59);
	std::uniform_int_distribution<int32_t> dist(-32768, 32767);
	for(unsigned k = 0; k < 10000; ++k)
	{
		std::vector<uint8_t> v, swapped;
		for(unsigned i = 0; i < 30; ++i)
		{
			const int32_t a = dist(rng);
			const int32_t b = dist(rng);
			Put(v, a); Put(v, b);
			Put(swapped, b); Put(swapped, a);
		}

		Stats a, b;
		assert(InspectS16LEStereo(v.data(), v.size(), a));
		assert(InspectS16LEStereo(swapped.data(), swapped.size(), b));
		const auto old = NativeLoop(v);
		assert(a.Envelope(0) == old[0] && a.Envelope(1) == old[1]);
		assert(a.Envelope(0) == b.Envelope(1));
		assert(a.Envelope(1) == b.Envelope(0));
		assert(a.channel[0].square_sum == b.channel[1].square_sum);
		assert(a.channel[1].square_sum == b.channel[0].square_sum);
	}

	for(unsigned inverted = 0; inverted < 2; ++inverted)
	{
		std::vector<uint8_t> v;
		for(unsigned i = 0; i < 3000; ++i)
		{
			const int32_t sample = static_cast<int32_t>(
				12000 * std::sin(2 * 3.141592653589793 * 120 * i / 3000));
			Put(v, sample);
			Put(v, inverted ? -sample : sample);
		}
		assert(InspectS16LEStereo(v.data(), v.size(), stats));
		assert(stats.Envelope(0) == stats.Envelope(1));
		assert(stats.channel[0].square_sum == stats.channel[1].square_sum);
	}

	std::cout << "PASS: haptics S16LE channel audit\n";
	return 0;
}
