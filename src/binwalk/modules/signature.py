# Basic signature scan module. This is the default (and primary) feature of binwalk.

# This module does not directly use the lzma module, but some plugins for this module do.
# If the lzma import fails, this module won't be loaded at all.
import lzma
import binwalk.core.magic
from binwalk.core.module import Module, Option, Kwarg

class Signature(Module):

    TITLE = "Signature Scan"
    ORDER = 10

    CLI = [
            Option(short='B',
                   long='signature',
                   kwargs={'enabled' : True, 'explicit_signature_scan' : True},
                   description='Scan target file(s) for common file signatures'),
            Option(short='R',
                   long='raw',
                   kwargs={'enabled' : True, 'raw_bytes' : ''},
                   type=str,
                   description='Scan target file(s) for the specified sequence of bytes'),
            Option(short='A',
                   long='opcodes',
                   kwargs={'enabled' : True, 'search_for_opcodes' : True},
                   description='Scan target file(s) for common executable opcode signatures'),
            #Option(short='C',
            #       long='cast',
            #       kwargs={'enabled' : True, 'cast_data_types' : True},
            #       description='Cast offsets as a given data type (use -y to specify the data type / endianness)'),
            Option(short='m',
                   long='magic',
                   kwargs={'enabled' : True, 'magic_files' : []},
                   type=list,
                   dtype='file',
                   description='Specify a custom magic file to use'),
            Option(short='b',
                   long='dumb',
                   kwargs={'dumb_scan' : True},
                   description='Disable smart signature keywords'),
        Option(short='I',
               long='invalid',
               kwargs={'show_invalid' : True},
               description='Show results marked as invalid'),
        Option(short='x',
               long='exclude',
               kwargs={'exclude_filters' : []},
               type=list,
               dtype=str.__name__,
               description='Exclude results that match <str>'),
        Option(short='y',
               long='include',
               kwargs={'include_filters' : []},
               type=list,
               dtype=str.__name__,
               description='Only show results that match <str>'),
    ]

    KWARGS = [
            Kwarg(name='enabled', default=False),
            Kwarg(name='show_invalid', default=False),
            Kwarg(name='include_filters', default=[]),
            Kwarg(name='exclude_filters', default=[]),
            Kwarg(name='raw_bytes', default=None),
            Kwarg(name='search_for_opcodes', default=False),
            Kwarg(name='explicit_signature_scan', default=False),
            Kwarg(name='cast_data_types', default=False),
            Kwarg(name='dumb_scan', default=False),
            Kwarg(name='magic_files', default=[]),
    ]

    VERBOSE_FORMAT = "%s    %d"

    def init(self):
        # If a raw byte sequence was specified, build a magic file from that instead of using the default magic files
        # TODO: re-implement this
        #if self.raw_bytes is not None:
        #    self.magic_files = [self.parser.file_from_string(self.raw_bytes)]

        # Append the user's magic file first so that those signatures take precedence
        if self.search_for_opcodes:
            self.magic_files = [
                    self.config.settings.user.binarch,
                    self.config.settings.system.binarch,
            ]

        elif self.cast_data_types:
            self.keep_going = True
            self.magic_files = [
                    self.config.settings.user.bincast,
                    self.config.settings.system.bincast,
            ]

        # Use the system default magic file if no other was specified, or if -B was explicitly specified
        if (not self.magic_files) or (self.explicit_signature_scan and not self.cast_data_types):
            self.magic_files.append(self.config.settings.user.binwalk)
            self.magic_files.append(self.config.settings.system.binwalk)

        # Initialize libmagic
        self.magic = binwalk.core.magic.Magic(include=self.include_filters,
                                              exclude=self.exclude_filters,
                                              invalid=self.show_invalid)

        # Parse the magic file(s)
        binwalk.core.common.debug("Loading magic files: %s" % str(self.magic_files))
        for f in self.magic_files:
            self.magic.load(f)

        self.VERBOSE = ["Signatures:", len(self.magic.signatures)]

    def validate(self, r):
        '''
        Called automatically by self.result.
        '''
        if self.show_invalid:
            r.valid = True
        elif r.valid:
            if not r.description:
                r.valid = False

            if r.size and (r.size + r.offset) > r.file.size:
                r.valid = False

            if r.jump and (r.jump + r.offset) > r.file.size:
                r.valid = False

    def scan_file(self, fp):
        current_file_offset = 0

        while True:
            (data, dlen) = fp.read_block()
            if not data:
                break

            current_block_offset = 0
            block_start = fp.tell() - dlen
            self.status.completed = block_start - fp.offset

            # TODO: Make magic scan return a results object.
            for r in self.magic.scan(data, dlen):

                # current_block_offset is set when a jump-to-offset keyword is encountered while
                # processing signatures. This points to an offset inside the current data block
                # that scanning should jump to, so ignore any subsequent candidate signatures that
                # occur before this offset inside the current data block.
                if r.offset < current_block_offset:
                    continue

                # Set the absolute offset inside the target file
                # TODO: Don't need the offset adjust stuff anymore, get rid of it
                r.offset = block_start + r.offset + r.adjust

                # Provide an instance of the current file object
                r.file = fp

                # Check if this was marked as invalid
                r.valid = (not r.invalid)

                # Register the result for futher processing/display
                # self.result automatically calls self.validate for result validation
                self.result(r=r)

                # Is this a valid result and did it specify a jump-to-offset keyword, and are we doing a "smart" scan?
                if r.valid and r.jump > 0 and not self.dumb_scan:
                    absolute_jump_offset = r.offset + r.jump
                    current_block_offset = candidate_offset + r.jump

                    # If the jump-to-offset is beyond the confines of the current block, seek the file to
                    # that offset and quit processing this block of data.
                    if absolute_jump_offset >= fp.tell():
                        fp.seek(r.offset + r.jump)
                        break

    def run(self):
        for fp in iter(self.next_file, None):
            self.header()
            self.scan_file(fp)
            self.footer()

