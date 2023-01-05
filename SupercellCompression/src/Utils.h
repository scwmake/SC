#pragma once
#include <stdlib.h>
#include <string>
#include <sstream>

namespace sc {
	// Small helper functions
	class Utils {
	public:
		static bool fileExist(std::string path);
		static std::string fileBasename(std::string filepath);
		static unsigned int Utils::fileSize(FILE*& file);
		static bool endsWith(std::string const& value, std::string const& ending);
	};

	// Buffer/File streams
	class IBinaryStream {
	public:
		virtual ~IBinaryStream() {};

		virtual size_t read(void* buff, size_t buffSize) = 0;
		virtual size_t write(void* buff, size_t buffSize) = 0;
		virtual long tell() = 0;
		virtual int set(int pos) = 0;
		virtual size_t size() = 0;
		virtual bool eof() = 0;
		virtual void setEof(size_t pos) = 0;
		virtual void close() = 0;
	};

	// Stream implementation for file
	class ScFileStream : public IBinaryStream {
	public:
		ScFileStream(FILE* input) {
			file = input;
		}

	private:
		FILE* file;
		size_t readEofOffset = 0;

	public:
		size_t read(void* buff, size_t buffSize) override {
			size_t finalPos = tell() + buffSize;
			const size_t readSize = fread(buff, 1, buffSize - (finalPos > size() ? finalPos - size() : 0), file);
			return readSize;
		};
		size_t write(void* buff, size_t buffSize) override {
			return fwrite(buff, 1, buffSize, file);
		};
		long tell() override {
			return ftell(file);
		};
		int set(int pos) override {
			return fseek(file, pos, SEEK_SET);
		};
		size_t size() override {
			return Utils::fileSize(file) - readEofOffset;
		};
		bool eof() override { 
			return size() <= tell() - readEofOffset; 
		};
		void setEof(size_t pos) override { 
			readEofOffset = pos;
		};
		void close() override {
			fclose(file);
		};
	};

	/*class ScBufferStream : public IBinaryStream {
	public:
		ScBufferStream(char* buff, size_t size) {
			buffer = buff;
			bufferSize = size;
		}

	private:
		char * buffer;
		size_t bufferSize;
		size_t readEofOffset = 0;
		size_t position = 0;

		std::stringstream stream;

	public:
		size_t read(void* buff, size_t buffSize) override {
			bool eof = tell() + buffSize > size();
			size_t toRead = eof ? size() - tell()  : buffSize;

			char* readBuffer = new char[buffSize]();

			for (size_t i = 0; toRead > i; i++) {
				readBuffer[i] = buffer[position];
				position++;
			}

			memcpy(buff, readBuffer, buffSize);
			delete[] readBuffer;

			return toRead;
		};
		size_t write(void* buff, size_t buffSize) override {
			char* data;
			data = (char*)buff;

			for (size_t i = 0; buffSize > i; i++) {
				buffer[position] = data[i];
				position++;
				if (eof()) {
					bufferSize++;
				}
			}

			return buffSize;
		};
		long tell() override {
			return position;
		};
		int set(int pos) override {
			if (size() > pos) {
				position = pos;
				return 0;
			} else {
				return 1;
			}
		};
		size_t size() override {
			return bufferSize;
		};
		bool eof() override { 
			return size() <= tell() - readEofOffset;
		}
		void setEof(size_t pos) override {
			readEofOffset = pos;
		};
		void close() override {
			free(buffer);
		};
	};*/

	// Structs

	// Data in .sc file header
	struct CompressedSwfProps {
		// Most likely randomly generated bytes. Must not contain zeros.
		// I think ID is a more appropriate name for this.
		// It may look like a hash, but it's definitely not it, at least because any data from the file does not fit it. 
		// And also confirmation of this guess can be the fact that the length of this alleged hash can be any, I think, for example, if there are a lot of files and it is difficult to generate a unique ID.
		char* id{};
		uint32_t idSize{0};

		// Hash from SIG
		char* hash{};
		uint32_t hashSize{0};

		// Metadata from version 4
		char* metadata{};
		uint32_t metadataSize{0};

		// Compress signature
		uint32_t signature{0};

		// Positive if data is real sc file
		bool ok{0};
	};

	// Error enums

	// Errors for Decompressor
	enum class DecompressorErrs {
		OK = 0,
		FILE_READ_ERROR = 1,
		FILE_WRITE_ERROR = 2,
		WRONG_FILE_ERROR = 3,
		DECOMPRESS_ERROR = 4
	};

	// Error for LZMA, LZHAM, ZSTD compression methods
	enum class CompressErrs {
		OK = 0,
		INIT_ERROR = 10,
		DATA_ERROR = 11,
		ALLOC_ERROR = 12
	};
}