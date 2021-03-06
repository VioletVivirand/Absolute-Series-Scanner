# Most code here is copyright (c) 2010 Plex Development Team. All rights reserved.
#
# Better ABsolute Scanner based on default scanner code from PMS 0.9.3.5 for Ubuntu
# 2011-10-15 by jmjf (on Plex Forums)
#
# a version of the Plex Series Scanner that does a better job of dealing with absolute numbered files
# and addresses the problem of series with numbers in the the name.
#
# Place this file in /var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Scanners/Series
# /var/lib/plexmediaserver is a.k.a. ~/ to the plex user
# you may have to create the Series subdirectory
#
# This code has only been tested on Ubuntu 10.4.2 with PMS 0.9.3.5 and my media collection. Use at your own risk.
# That said, I expect it will work on other platforms.
#
# all debug messages are left in -- will only show on console -- include BABS: at beginning of line
# all changes except debug messages are called out with comments begining # BABS -- 
#
import re, os, os.path
import Media, VideoFiles, Stack, Utils
from mp4file import mp4file, atomsearch
import re, time, unicodedata, hashlib, types
import zipfile, urllib2, cStringIO
from lxml import etree

# Define proxy for TVDB.
TVDB_SITE  = 'thetvdb.com'
TVDB_PROXY = 'thetvdb.plexapp.com'

TVDB_API_KEY    = 'D4DDDAEFAD083E6F'
TVDB_SEARCH_URL = 'http://%s/api/GetSeries.php?seriesname=%%s&language=%%s' % TVDB_PROXY 
TVDB_ADVSEARCH_NETWORK  = 'http://%s/index.php?seriesname=%%s&fieldlocation=1&genre=&year=%%s&network=%%s&zap2it_id=&tvcom_id=&imdb_id=&order=translation&searching=Search&tab=advancedsearch&language=%%s' % TVDB_PROXY

TVDB_GUID_SEARCH  = 'http://freebase.plexapp.com/tv/guid/'
TVDB_QUICK_SEARCH = 'http://freebase.plexapp.com/tv/names/'
TVDB_TITLE_SEARCH = 'http://freebase.plexapp.com/tv/titles/'

TVDB_SERIES_URL = '%%s/api/%s/series/%%s' % TVDB_API_KEY
TVDB_ZIP_URL    = '%s/all/%%s.zip' % TVDB_SERIES_URL
TVDB_SERIES_URL = '%s/%%s.xml' % TVDB_SERIES_URL
TVDB_BANNER_URL = '%s/banners/'

GOOGLE_JSON_TVDB = 'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&rsz=large&q=%s+"thetvdb.com"+series+%s'
GOOGLE_JSON_TVDB_TITLE = 'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&rsz=large&q=%s+"thetvdb.com"+series+info+%s'
GOOGLE_JSON_BROAD = 'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&rsz=large&q=%s+site:thetvdb.com+%s'
GOOGLE_JSON_IMDB = 'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&rsz=large&q=%s+site:imdb.com+tv+%s'

Dict = dict()
Dict['ZIP_MIRROR'] = 'http://' + TVDB_PROXY
lang = 'en'

TOTAL_TRIES = 1

THETVDB_LANGUAGES_CODE = {
  'cs': '28',
  'da': '10',
  'de': '14',
  'el': '20',
  'en': '7',
  'es': '16',
  'fi': '11',
  'fr': '17',
  'he': '24',
  'hu': '19',
  'it': '15',
  'ja': '25',
  'nl': '13',
  'no': '9',
  'pl': '18',
  'pt': '26',
  'ru': '22',
  'sv': '8',
  'tr': '21',
  'zh': '6',
}

episode_regexps = [
    '(?P<show>.*?)[sS](?P<season>[0-9]+)[\._ ]*[eE](?P<ep>[0-9]+)([- ]?[Ee+](?P<secondEp>[0-9]+))?',                           # S03E04-E05
    '(?P<show>.*?)[sS](?P<season>[0-9]{2})[\._\- ]+(?P<ep>[0-9]+)',                                                            # S03-03
    '(?P<show>.*?)([^0-9]|^)(?P<season>[0-9]{1,2})[Xx](?P<ep>[0-9]+)(-[0-9]+[Xx](?P<secondEp>[0-9]+))?'                        # 3x03
  ]
# BABS -- Removed the ".602." expresion from the list above. See default scanner to recover it.

date_regexps = [
    '(?P<year>[0-9]{4})[^0-9a-zA-Z]+(?P<month>[0-9]{2})[^0-9a-zA-Z]+(?P<day>[0-9]{2})([^0-9]|$)',                # 2009-02-10
    '(?P<month>[0-9]{2})[^0-9a-zA-Z]+(?P<day>[0-9]{2})[^0-9a-zA-Z(]+(?P<year>[0-9]{4})([^0-9a-zA-Z]|$)', # 02-10-2009
  ]

standalone_episode_regexs = [
  '(.*?)( \(([0-9]+)\))? - ([0-9]+)+x([0-9]+)(-[0-9]+[Xx]([0-9]+))?( - (.*))?',  # Newzbin style, no _UNPACK_
  '(.*?)( \(([0-9]+)\))?[Ss]([0-9]+)+[Ee]([0-9]+)(-[0-9]+[Xx]([0-9]+))?( - (.*))?'   # standard s00e00
  ]
  
season_regex = '.*?(?P<season>[0-9]+)$' # folder for a season

just_episode_regexs = [
    '(?P<ep>[0-9]{1,3})[\. -_]of[\. -_]+[0-9]{1,3}',       # 01 of 08
    '^(?P<ep>[0-9]{1,3})[^0-9]',                           # 01 - Foo
    '(^|[ \.\-_])e(p{0,1}|(pisode){0,1})[ \.\-_]*(?P<ep>[0-9]{2,3})([^0-9c-uw-z%]|$)', # Blah Blah ep234
    '.*?[ \.\-_](?P<ep>[0-9]{2,3})[^0-9c-uw-z%]+',         # Flah - 04 - Blah
    '.*?[ \.\-_](?P<ep>[0-9]{2,3})$',                      # Flah - 04
    '.*?[^0-9x](?P<ep>[0-9]{2,3})$'                        # Flah707
  ]
# BABS -- modified "Blah Blah ep234" expression to only look for e, ep, or episode -- original scanner looked for e followed by 0 or more a-z

ends_with_number = '.*([0-9]{1,2})$'

ends_with_episode = ['[ ]*[0-9]{1,2}x[0-9]{1,3}$', '[ ]*S[0-9]+E[0-9]+$']



# Look for episodes.
def Scan(path, files, mediaList, subdirs):
  sortToSeasons = False
  print "BABS: Scan"
  episode_dict = dict()
  
  #If we have a tvdb.id file, then use that for determining the metadata
  	      
  # Code to get the tvdb id for this item.  This checks to see if the tvdb.id file exists in the same directory as the first file in the to-scan list
  # which will work fine, as long as the files are in the root folder (which they should be for absolute numbering).  For stuff sorted in a season format, 
  # the tvdb.id would have to be in the Season 0 or Season 1 folder (i.e. Season 0, if it exists, otherwise Season 1).
  try:
    the_dir = os.path.dirname(files[0])	     		      
    if os.path.exists(the_dir + '//' + 'tvdb.id'):
      fo = open(os.path.realpath(the_dir + '//' + 'tvdb.id'),'rb') 
      tvdb_id = fo.readline()
      episode_dict = GetEpisodesBySeriesID(tvdb_id)
      sortToSeasons = True
  except:
    pass
	

  # Scan for video files.
  VideoFiles.Scan(path, files, mediaList, subdirs, "")
  
  # Take top two as show/season, but require at least the top one.
  paths = Utils.SplitPath(path)

  if len(paths) == 1 and len(paths[0]) == 0:

    print "BABS: len(paths) == 1 and len(paths[0]) == 0"
  
    # Run the select regexps we allow at the top level.
    for i in files:
      file = os.path.basename(i)
      full_path = os.path.realpath(i)

      print "BABS: tlrs os.path.basename, i = |", i, "| file = |", file, "|"

      for rx in episode_regexps[0:-1]:
        match = re.search(rx, file, re.IGNORECASE)
        if match:

          print "BABS: matched episode_regexps: ", rx
          
          # Extract data.
          show = match.group('show')
          season = int(match.group('season'))
          episode = int(match.group('ep'))
          endEpisode = episode
          if match.groupdict().has_key('secondEp') and match.group('secondEp'):
            endEpisode = int(match.group('secondEp'))
          
          # Clean title.
          name, year = VideoFiles.CleanName(show)
          for ep in range(episode, endEpisode+1):
            tv_show = Media.Episode(name, season, ep, '', year)
            tv_show.display_offset = (ep-episode)*100/(endEpisode-episode+1)
            tv_show.parts.append(i)
            mediaList.append(tv_show)
  
  elif len(paths) > 0 and len(paths[0]) > 0:

    print "BABS: len(paths) > 0 and len(paths[0]) > 0"

    done = False
        
    # See if parent directory is a perfect match (e.g. a directory like "24 - 8x02 - Day 8_ 5_00P.M. - 6_00P.M")
    if len(files) == 1:
      for rx in standalone_episode_regexs:
        res = re.findall(rx, paths[-1])
        if len(res):

          print "BABS: match on standalone_episode_regexs ", rx

          show, junk, year, season, episode, junk, endEpisode, junk, title = res[0]
          
          # If it didn't have a show, then grab it from the directory.
          if len(show) == 0:
            (show, year) = VideoFiles.CleanName(paths[0])

            print "BABS: standalone, show from directory, show = |", show, "| year = |", year, "|"
            
          episode = int(episode)
          if len(endEpisode) > 0:
            endEpisode = int(endEpisode)
          else:
            endEpisode = episode
            
          for ep in range(episode, endEpisode+1):
            tv_show = Media.Episode(show, season, ep, title, year)
            tv_show.display_offset = (ep-episode)*100/(endEpisode-episode+1)
            tv_show.parts.append(files[0])
            mediaList.append(tv_show)
            
          done = True
          break
          
    if done == False:

      # Not a perfect standalone match, so get information from directories. (e.g. "Lost/Season 1/s0101.mkv")
      season = None
      seasonNumber = None

      (show, year) = VideoFiles.CleanName(paths[0])

      print "BABS: not perfect match: show = |", show, "| year = |", year, "|"
      
      # Which component looks like season?
      if len(paths) >= 2:

        print "BABS: len(paths) >= 2"

        season = paths[len(paths)-1]
        match = re.match(season_regex, season, re.IGNORECASE)
        if match:
          seasonNumber = int(match.group('season'))

          print "BABS: matched season_regex with season = |", season, "| seasonNumber =", seasonNumber 

      print "BABS: before ends_with_episode, show = |", show, "|"

      # Make sure an episode name didn't make it into the show.
      for rx in ends_with_episode:
        show = re.sub(rx, '', show)

      print "BABS: after ends_with_episode, show = |", show, "|"

      for i in files:
        done = False
        file = os.path.basename(i)

        print "BABS: os.path.basename, i = |", i, "| file = |", file, "|"

        (file, ext) = os.path.splitext(file)

        print "BABS: os.path.splitext, file = |", file, "| ext = |", ext, "|"
        
        if ext.lower() in ['.mp4', '.m4v', '.mov']:

          print "BABS: try mp4 tags"

          m4season = m4ep = m4year = 0
          m4show = title = ''
          try: 
            mp4fileTags = mp4file.Mp4File(i)
            
            # Show.
            try: m4show = find_data(mp4fileTags, 'moov/udta/meta/ilst/tvshow').encode('utf-8')
            except: pass
              
            # Season.
            try: m4season = int(find_data(mp4fileTags, 'moov/udta/meta/ilst/tvseason'))
            except: pass
              
            # Episode.
            m4ep = None
            try:
              # tracknum (can be 101)
              m4ep = int(find_data(mp4fileTags, 'moov/udta/meta/ilst/tracknum'))
            except:
              try:
                # tvepisodenum (can be S2E16)
                m4ep = find_data(mp4fileTags, 'moov/udta/meta/ilst/tvepisodenum')
              except:
                # TV Episode (can be 101)
                m4ep = int(find_data(mp4fileTags, 'moov/udta/meta/ilst/tvepisode'))
            
            if m4ep is not None:
              found = False
              try:
                # See if it matches regular expression.
                for rx in episode_regexps[:-1]:
                  match = re.search(rx, file, re.IGNORECASE)
                  if match:
                    m4season = int(match.group('season'))
                    m4ep = int(match.group('ep'))
                    found = True
              
                if found == False and re.match('[0-9]+', str(m4ep)):
                  # Carefully convert to episode number.
                  m4ep = int(m4ep) % 100
                elif found == False:
                  m4ep = int(re.findall('[0-9]+', m4ep)[0])
              except:
                pass

            # Title.
            try: title = find_data(mp4fileTags, 'moov/udta/meta/ilst/title').encode('utf-8')
            except: pass
              
            # Year.
            try: m4year = int(find_data(mp4fileTags, 'moov/udta/meta/ilst/year')[:4])
            except: pass

            # If we have all the data we need, add it.
            if len(m4show) > 0 and m4season > 0 and m4ep > 0:
              tv_show = Media.Episode(m4show, m4season, m4ep, title, m4year)
              tv_show.parts.append(i)
              mediaList.append(tv_show)
              continue

          except:
            pass
        
        # Check for date-based regexps first.
        for rx in date_regexps:
          match = re.search(rx, file)
          if match:

            print "BABS: matched date_regexps ", rx

            year = int(match.group('year'))
            month = int(match.group('month'))
            day = int(match.group('day'))

            # Use the year as the season.
            tv_show = Media.Episode(show, year, None, None, None)
            tv_show.released_at = '%d-%02d-%02d' % (year, month, day)
            tv_show.parts.append(i)
            mediaList.append(tv_show)

            done = True
            break

        if done == False:

          # Take the year out, because it's not going to help at this point.
          cleanName, cleanYear = VideoFiles.CleanName(file)

          print "BABS: after CleanName file = |", file, "| cleanName = |", cleanName, "| cleanYear = |", cleanYear, "|"

          if cleanYear != None:
            file = file.replace(str(cleanYear), 'XXXX')

            print "BABS: replaced year, file = |", file, "|"
          
          # Minor cleaning on the file to avoid false matches on H.264, 720p, etc.
          whackRx = ['([hHx][\.]?264)[^0-9]', '[^[0-9](720[pP])', '[^[0-9](1080[pP])', '[^[0-9](480[pP])']
          for rx in whackRx:
            file = re.sub(rx, ' ', file)

          print "BABS: after whackRx, file = |", file, "|"
          
          for rx in episode_regexps:
            
            match = re.search(rx, file, re.IGNORECASE)
            if match:

              print "BABS: matched episode_regexps ", rx

              # Parse season and episode.
              the_season = int(match.group('season'))
              episode = int(match.group('ep'))
              endEpisode = episode
              if match.groupdict().has_key('secondEp') and match.group('secondEp'):
                endEpisode = int(match.group('secondEp'))
                
              # More validation for the weakest regular expression.
              if rx == episode_regexps[-1]:
                
                # Look like a movie? Skip it.
                if re.match('.+ \([1-2][0-9]{3}\)', paths[-1]):
                  done = True
                  break
                  
                # Skip episode 0 on the weak regex since it's pretty much never right.
                if the_season == 0:
                  break
                  
                # Make sure this isn't absolute order.
                if seasonNumber is not None:
                  if seasonNumber != the_season:
                    # Something is amiss, see if it starts with an episode numbers.
                    if re.search('^[0-9]+ -', file):
                      # Let the episode matcher have it.
                      break
                    
                    # Treat the whole thing as an episode.
                    episode = episode + the_season*100
                    if endEpisode is not None:
                      endEpisode = endEpisode + the_season*100

              for ep in range(episode, endEpisode+1):
                tv_show = Media.Episode(show, the_season, ep, None, year)
                tv_show.display_offset = (ep-episode)*100/(endEpisode-episode+1)
                tv_show.parts.append(i)
                mediaList.append(tv_show)
              
              done = True
              break
              
        if done == False:

          print "BABS: dealing with episode? file = |", file, "|"

          # BABS -- Before we do CleanName, which will remove any dashes, etc. in filename, attempt to remove series name found in directory
          file = re.sub(show, 'X', file)
          print "BABS: before CleanName, remove show, show = |", show, "| file = |", file, "|"

          # OK, next let's see if we're dealing with something that looks like an episode.
          # Begin by cleaning the filename to remove garbage like "h.264" that could throw
          # things off.
          #
          (file, year) = VideoFiles.CleanName(file)

          print "BABS: episodes: CleanName: file = |", file, "| year = |", year, "|"

          # BABS -- And do it again, just in case the directory is off by things CleanName handles
          file = re.sub(show, 'X', file)
          print "BABS: after CleanName, remove show, show = |", show, "| file = |", file, "|"
          
          for rx in just_episode_regexs:
            episode_match = re.search(rx, file, re.IGNORECASE)
            if episode_match is not None:

              print "BABS: matched just_episode_regexs ", rx
              
              if sortToSeasons is False:
                  the_episode = int(episode_match.group('ep'))
                  the_season = 1
              else:
                the_season = episode_dict[int(episode_match.group('ep'))][0]
                the_episode = episode_dict[int(episode_match.group('ep'))][1]

              print "BABS: the_season =", the_season
              print "BABS: show = |", show, "| the_episode =", the_episode
              
              # Now look for a season.
              if seasonNumber is not None:
                the_season = seasonNumber

                print "BABS: seasonNumber is not None, the_season = ", the_season
                
                # See if we accidentally parsed the episode as season.
                if the_episode >= 100 and int(the_episode / 100) == the_season:
                  the_episode = the_episode % 100

                  print "BABS: the_episode % 100 =", the_episode
              
              tv_show = Media.Episode(show, the_season, the_episode, None, None)
              tv_show.parts.append(i)
              mediaList.append(tv_show)
              done = True
              break
          
        if done == False:
          print "Got nothing for:", file
          
  # Stack the results.
  Stack.Scan(path, files, mediaList, subdirs)
  
def find_data(atom, name):
  child = atomsearch.find_path(atom, name)
  data_atom = child.find('data')
  if data_atom and 'data' in data_atom.attrs:
    return data_atom.attrs['data']




headers = {'User-agent': 'Plex/Nine'}
def GetResultFromNetwork(url, fetchContent=True):
  global successCount, failureCount, RETRY_TIMEOUT
 
  # Not sure where this is introduced, but avoid spaces.
  #url = url.replace(' ','+')
  
  
  #try:    
  tries = TOTAL_TRIES
  while tries > 0:
    result = urllib2.urlopen(url)    
    return result


def fixBrokenXml(xml):
  if xml.count('<?xml') > 1:
    xml = xml[xml.rfind('<?xml'):]
    if xml.count('</Data>') > 1:
      xml = xml[:-7]
  return xml


def GetEpisodesBySeriesID( seriesID):
   # Convenience function
  el_text = lambda element, xp: element.xpath(xp)[0].text if element.xpath(xp)[0].text else '' 
  
  
   # Get the show's zipped data
  zip_url = TVDB_ZIP_URL % (Dict['ZIP_MIRROR'], seriesID, lang)   
  zip_data = cStringIO.StringIO(GetResultFromNetwork(zip_url).read())
  with zipfile.ZipFile(zip_data) as zip_archive:
	zip_archive_mem = cStringIO.StringIO(zip_archive.read(lang+'.xml'))
  
  zip_archive_mem = zip_archive_mem.read()
  
  #Test to make sure file is correct
  #f = open('//media//IDRIVE//en.xml', 'w')
  #f.write(zip_archive_mem)
  
  #zip_archive = Archive.Zip(zip_data)
    
   # Extract the XML files from the archive. Work around corrupt XML.
  root_el = etree.fromstring(fixBrokenXml(zip_archive_mem))
  series_el = root_el.xpath('Episode')
  # Get list of all episodes and match their season/episode number to absolute number
  

  #Store the results in a dict so we can look for the season/episode for a particular absolute number
  episode_dict = dict()
  for episode_el in series_el:
    absolute_num = el_text(episode_el, 'absolute_number')
    season_num = el_text(episode_el, 'SeasonNumber')
    episode_num = el_text(episode_el,'EpisodeNumber')
    #We only store the episode in dictionary if it *has* an absolute number
    if absolute_num.isdigit():
      episode_dict[int(absolute_num)] = [season_num, episode_num]
    
  return episode_dict    
      
import sys
    
if __name__ == '__main__':
  print "Hello, world!"
  path = sys.argv[1]
  files = [os.path.join(path, file) for file in os.listdir(path)]
  media = []
  Scan(path[1:], files, media, [])
  print "Media:", media
