#pragma once

#include "Utils.h"

namespace sc {
	class ZSTD {
	public:
		static CompressionErrs decompress(IBinaryStream& inStream, IBinaryStream& outStream);
		static CompressionErrs compress(IBinaryStream& inStream, IBinaryStream& outStream);
	};
}
